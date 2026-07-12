"""REST API for the public chronos_forecaster package."""

from __future__ import annotations

import json
import os
from functools import lru_cache
from importlib.metadata import version
from threading import Lock
from typing import Any, Literal

import pandas as pd
import uvicorn
from chronos_forecaster import ChronosForecaster
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ConfigDict, Field


class ForecastRequest(BaseModel):
    """Input data and the matching Chronos configuration."""

    model_config = ConfigDict(extra="forbid")

    data: list[dict[str, Any]] = Field(min_length=1)
    forecast_horizon: int = Field(gt=0)
    datetime_col: str = "date"
    target_col: str = "target"
    item_id_col: str | None = None
    frequency: str = "h"
    random_state: int | None = None
    engine: Literal["chronos", "chronos2"] = "chronos2"
    past_covariates: list[dict[str, Any]] | None = None
    future_covariates: list[dict[str, Any]] | None = None


class ForecastResponse(BaseModel):
    predictions: list[dict[str, Any]]


@lru_cache(maxsize=8)
def get_forecaster(
    forecast_horizon: int,
    datetime_col: str,
    target_col: str,
    item_id_col: str | None,
    frequency: str,
    random_state: int | None,
    engine: str,
) -> ChronosForecaster:
    """Reuse loaded models for repeated configurations."""
    return ChronosForecaster(
        forecast_horizon=forecast_horizon,
        datetime_col=datetime_col,
        target_col=target_col,
        item_id_col=item_id_col,
        frequency=frequency,
        random_state=random_state,
        engine=engine,
    )


app = FastAPI(
    title="Forecast Engine",
    summary="Time-series forecasting with Chronos",
    description=(
        "Generate forecasts with `chronos_forecaster` through JSON or upload a "
        "CSV directly using **POST /forecast/csv**. Models are cached while the "
        "server is running."
    ),
    version="0.1.0",
    openapi_tags=[
        {"name": "Forecasts", "description": "Generate time-series forecasts."},
        {"name": "System", "description": "Check service readiness."},
    ],
)
_forecast_lock = Lock()


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    """Open the interactive API documentation by default."""
    return RedirectResponse(url="/docs")


@app.get("/health", tags=["System"], summary="Check server readiness")
def health() -> dict[str, Any]:
    """Report readiness without downloading a model."""
    return {
        "status": "ok",
        "chronos_forecaster_version": version("chronos_forecaster"),
        "cached_configurations": get_forecaster.cache_info().currsize,
    }


def _as_dataframe(
    records: list[dict[str, Any]] | None,
    name: str,
    required_columns: set[str],
) -> pd.DataFrame | None:
    if records is None:
        return None

    frame = pd.DataFrame(records)
    missing = required_columns - set(frame.columns)
    if missing:
        raise HTTPException(
            status_code=422,
            detail=f"{name} is missing columns: {', '.join(sorted(missing))}",
        )
    return frame


def _normalize_timestamps(
    frame: pd.DataFrame | None, name: str, datetime_col: str
) -> pd.DataFrame | None:
    if frame is None:
        return None

    try:
        timestamps = pd.to_datetime(frame[datetime_col], utc=True)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=422,
            detail=f"{name} has invalid timestamps in column '{datetime_col}': {exc}",
        ) from exc

    normalized = frame.copy()
    normalized[datetime_col] = timestamps.dt.tz_localize(None)
    return normalized


@app.post(
    "/forecast",
    response_model=ForecastResponse,
    tags=["Forecasts"],
    summary="Forecast from JSON observations",
)
def forecast(request: ForecastRequest) -> ForecastResponse:
    """Generate a point forecast and 80% prediction interval."""
    required = {request.datetime_col, request.target_col}
    if request.item_id_col:
        required.add(request.item_id_col)

    data = _normalize_timestamps(
        _as_dataframe(request.data, "data", required), "data", request.datetime_col
    )
    covariate_columns = {request.datetime_col}
    if request.item_id_col:
        covariate_columns.add(request.item_id_col)

    past = _normalize_timestamps(
        _as_dataframe(request.past_covariates, "past_covariates", covariate_columns),
        "past_covariates",
        request.datetime_col,
    )
    future = _normalize_timestamps(
        _as_dataframe(request.future_covariates, "future_covariates", covariate_columns),
        "future_covariates",
        request.datetime_col,
    )

    if request.engine == "chronos" and (past is not None or future is not None):
        raise HTTPException(
            status_code=422,
            detail="Covariates require engine='chronos2'.",
        )

    forecaster = get_forecaster(
        request.forecast_horizon,
        request.datetime_col,
        request.target_col,
        request.item_id_col,
        request.frequency,
        request.random_state,
        request.engine,
    )

    try:
        # The underlying pipelines are shared and should not run concurrently.
        with _forecast_lock:
            result = forecaster.predict(
                data,
                past_covariates_df=past,
                future_covariates_df=future,
            )
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # chronos_forecaster 0.2.2 omits the series key from panel output.
    if request.item_id_col and request.item_id_col not in result.columns:
        item_ids = data[request.item_id_col].drop_duplicates().tolist()
        expected_rows = len(item_ids) * request.forecast_horizon
        if len(result) != expected_rows:
            raise HTTPException(
                status_code=500,
                detail="Unexpected number of rows in panel forecast.",
            )
        result.insert(
            0,
            request.item_id_col,
            [item_id for item_id in item_ids for _ in range(request.forecast_horizon)],
        )

    predictions = json.loads(result.to_json(orient="records", date_format="iso"))
    return ForecastResponse(predictions=predictions)


@app.post(
    "/forecast/csv",
    response_model=ForecastResponse,
    tags=["Forecasts"],
    summary="Upload a CSV and generate a forecast",
    description=(
        "Upload the historical target data and, for Chronos-2, optional past "
        "and future covariate CSVs. Identify the timestamp, target, and optional "
        "series ID columns, then execute the request directly from Swagger UI."
    ),
)
def forecast_csv(
    file: UploadFile = File(description="CSV containing timestamps and target values"),
    past_covariates_file: UploadFile | None = File(
        None, description="Optional CSV with historical Chronos-2 covariates"
    ),
    future_covariates_file: UploadFile | None = File(
        None, description="Optional CSV with known future Chronos-2 covariates"
    ),
    datetime_col: str = Form("date", description="Timestamp column name"),
    target_col: str = Form("target", description="Value column name"),
    item_id_col: str = Form(
        "", description="Series ID column; leave blank for one series"
    ),
    forecast_horizon: int = Form(24, gt=0, description="Future steps to predict"),
    frequency: str = Form("h", description="Pandas frequency, for example h or D"),
    engine: Literal["chronos", "chronos2"] = Form("chronos2"),
    random_state: int = Form(42, description="Random seed"),
) -> ForecastResponse:
    """Convert an uploaded CSV into the regular forecast request."""
    data = _read_csv(file, "file")
    past_covariates = _read_csv(past_covariates_file, "past_covariates_file")
    future_covariates = _read_csv(future_covariates_file, "future_covariates_file")

    return forecast(
        ForecastRequest(
            data=data,
            forecast_horizon=forecast_horizon,
            datetime_col=datetime_col,
            target_col=target_col,
            item_id_col=item_id_col or None,
            frequency=frequency,
            random_state=random_state,
            engine=engine,
            past_covariates=past_covariates,
            future_covariates=future_covariates,
        )
    )


def _read_csv(upload: UploadFile | None, name: str) -> list[dict[str, Any]] | None:
    if upload is None:
        return None

    try:
        return pd.read_csv(upload.file).to_dict(orient="records")
    except (UnicodeDecodeError, pd.errors.EmptyDataError, pd.errors.ParserError) as exc:
        raise HTTPException(status_code=422, detail=f"Invalid {name}: {exc}") from exc


if __name__ == "__main__":
    uvicorn.run(
        app,
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
    )
