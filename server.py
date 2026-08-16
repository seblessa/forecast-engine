"""Thin FastAPI transport layer over the reusable Forecast Engine core."""

from __future__ import annotations

import logging
import json
import os
from importlib.metadata import version
from secrets import compare_digest
from threading import Lock
from typing import Annotated, Any, Literal

import pandas as pd
import uvicorn
from fastapi import APIRouter, Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, field_validator

from forecast_engine import ForecastEngine
from forecast_engine.errors import ForecastValidationError


logger = logging.getLogger(__name__)


class ForecastRequest(BaseModel):
    """Historical singular-target contract kept for existing consumers."""

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


class V2ForecastRequest(BaseModel):
    """Generic target-list contract for new consumers."""

    model_config = ConfigDict(extra="forbid")

    data: list[dict[str, Any]] = Field(min_length=1)
    target_cols: list[str] = Field(min_length=1)
    forecast_horizon: int = Field(gt=0)
    datetime_col: str = "date"
    item_id_col: str | None = None
    frequency: str = "h"
    model: str = "chronos2"
    future_data: list[dict[str, Any]] | None = None
    quantile_levels: list[float] = Field(
        default_factory=lambda: [0.1, 0.5, 0.9], min_length=1
    )
    batch_size: int = Field(default=256, gt=0)
    context_length: int | None = Field(default=None, gt=0)
    cross_learning: bool = False

    @field_validator("target_cols")
    @classmethod
    def validate_target_cols(cls, values: list[str]) -> list[str]:
        if any(not isinstance(value, str) or not value for value in values):
            raise ValueError("target_cols must contain non-empty strings")
        if len(set(values)) != len(values):
            raise ValueError("target_cols must not contain duplicates")
        return values

    @field_validator("quantile_levels")
    @classmethod
    def validate_quantile_levels(cls, values: list[float]) -> list[float]:
        if any(not 0.0 < value < 1.0 for value in values):
            raise ValueError("quantile_levels must be strictly between 0 and 1")
        if len(set(values)) != len(values):
            raise ValueError("quantile_levels must not contain duplicates")
        return values


class ForecastResponse(BaseModel):
    predictions: list[dict[str, Any]]


class V2Prediction(BaseModel):
    timestamp: str
    item_id: Any | None = None
    target_name: str
    prediction: float
    quantiles: dict[str, float]


class V2ForecastResponse(BaseModel):
    predictions: list[V2Prediction]


class ModelCapabilities(BaseModel):
    id: str
    model_id: str
    multivariate: bool
    covariates: bool
    cross_learning: bool
    panel: bool
    context_length: bool
    legacy_aliases: list[str]


class ModelsResponse(BaseModel):
    models: list[ModelCapabilities]


forecast_engine = ForecastEngine(
    device=os.getenv("FORECAST_DEVICE"),
    dtype=os.getenv("FORECAST_DTYPE"),
    revision=os.getenv("FORECAST_MODEL_REVISION"),
)
_forecast_lock = Lock()
_saas_bearer = HTTPBearer(auto_error=False)


def require_saas_auth(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(_saas_bearer)
    ],
) -> None:
    """Require the shared SaaS bearer token without exposing it in logs."""
    expected_token = os.getenv("SAAS_API_TOKEN")
    if not expected_token:
        raise HTTPException(
            status_code=503,
            detail="SaaS authentication is not configured.",
        )

    if (
        credentials is None
        or credentials.scheme.lower() != "bearer"
        or not compare_digest(credentials.credentials, expected_token)
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )


saas_router = APIRouter(
    prefix="/v1/saas",
    tags=["SaaS"],
    dependencies=[Depends(require_saas_auth)],
)

app = FastAPI(
    title="Forecast Engine",
    summary="Time-series forecasting with official Amazon Chronos pipelines",
    description=(
        "Generate forecasts through the reusable Forecast Engine core. "
        "Use **POST /v2/forecast** for new integrations; the original "
        "`/forecast` and `/forecast/csv` contracts remain supported."
    ),
    version="0.2.0",
    openapi_tags=[
        {
            "name": "Forecasts",
            "description": "Legacy and generic time-series forecasting endpoints.",
        },
        {
            "name": "Models",
            "description": "Configured model aliases and capabilities.",
        },
        {
            "name": "SaaS",
            "description": "Authenticated compatibility routes for the SaaS client.",
        },
        {"name": "System", "description": "Check service readiness."},
    ],
)


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    """Open the interactive API documentation by default."""
    return RedirectResponse(url="/docs")


@app.get("/health", tags=["System"], summary="Check server readiness")
def health() -> dict[str, Any]:
    """Report readiness without downloading a model."""
    return {
        "status": "ok",
        "forecast_engine_version": "0.2.0",
        "chronos_forecasting_version": version("chronos-forecasting"),
        "loaded_model_aliases": forecast_engine.pipeline_manager.loaded_aliases,
        "cached_pipelines": forecast_engine.pipeline_manager.cached_pipeline_count,
        # Keep the old cache metric name for consumers that only inspect it.
        "cached_configurations": forecast_engine.pipeline_manager.cached_pipeline_count,
    }


@app.get(
    "/models",
    response_model=ModelsResponse,
    tags=["Models"],
    summary="List configured forecasting models",
)
def models() -> ModelsResponse:
    """List aliases without loading model weights."""
    return ModelsResponse(
        models=[
            ModelCapabilities(
                id=spec.alias,
                model_id=spec.model_id,
                multivariate=spec.multivariate,
                covariates=spec.covariates,
                cross_learning=spec.cross_learning,
                panel=spec.panel,
                context_length=spec.context_length,
                legacy_aliases=list(spec.legacy_aliases),
            )
            for spec in forecast_engine.registry.specs()
        ]
    )


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
        timestamps = pd.to_datetime(frame[datetime_col], utc=True, errors="raise")
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=422,
            detail=f"{name} has invalid timestamps in column '{datetime_col}': {exc}",
        ) from exc
    if timestamps.isna().any():
        raise HTTPException(
            status_code=422,
            detail=f"{name} has missing timestamps in column '{datetime_col}'",
        )

    normalized = frame.copy()
    normalized[datetime_col] = timestamps.dt.tz_localize(None)
    return normalized


class _LegacyForecaster:
    """Small compatibility object retained for the historical route adapter."""

    def __init__(
        self,
        *,
        datetime_col: str,
        target_col: str,
        item_id_col: str | None,
        frequency: str,
        forecast_horizon: int,
        engine: Literal["chronos", "chronos2"],
    ) -> None:
        self.datetime_col = datetime_col
        self.target_col = target_col
        self.item_id_col = item_id_col
        self.frequency = frequency
        self.forecast_horizon = forecast_horizon
        self.engine = engine

    def predict(
        self,
        data: pd.DataFrame,
        *,
        past_covariates_df: pd.DataFrame | None = None,
        future_covariates_df: pd.DataFrame | None = None,
    ) -> pd.DataFrame:
        return forecast_engine.forecast_legacy(
            data=data,
            datetime_col=self.datetime_col,
            target_col=self.target_col,
            item_id_col=self.item_id_col,
            frequency=self.frequency,
            forecast_horizon=self.forecast_horizon,
            engine=self.engine,
            past_covariates=past_covariates_df,
            future_covariates=future_covariates_df,
        )


def get_forecaster(
    forecast_horizon: int,
    datetime_col: str,
    target_col: str,
    item_id_col: str | None,
    frequency: str,
    random_state: int | None,
    engine: str,
) -> _LegacyForecaster:
    """Build a request adapter; model weights are cached by ``forecast_engine``."""
    del random_state
    return _LegacyForecaster(
        datetime_col=datetime_col,
        target_col=target_col,
        item_id_col=item_id_col,
        frequency=frequency,
        forecast_horizon=forecast_horizon,
        engine=engine,  # type: ignore[arg-type]
    )


def _raise_forecast_error(exc: Exception) -> None:
    if isinstance(exc, (ForecastValidationError, KeyError, TypeError, ValueError)):
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    logger.exception("Forecast inference failed")
    raise HTTPException(status_code=500, detail="Forecast inference failed.") from exc


def _run_forecast(request: ForecastRequest) -> ForecastResponse:
    """Run the legacy contract through the shared core and preserve its output."""
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

    try:
        with _forecast_lock:
            forecaster = get_forecaster(
                request.forecast_horizon,
                request.datetime_col,
                request.target_col,
                request.item_id_col,
                request.frequency,
                request.random_state,
                request.engine,
            )
            result = forecaster.predict(
                data,
                past_covariates_df=past,
                future_covariates_df=future,
            )
    except Exception as exc:  # noqa: BLE001 - converted at the transport boundary
        _raise_forecast_error(exc)

    if request.item_id_col and request.item_id_col not in result.columns:
        item_ids = data[request.item_id_col].drop_duplicates().tolist()
        expected_rows = len(item_ids) * request.forecast_horizon
        if len(result) != expected_rows:
            raise HTTPException(
                status_code=500,
                detail="Unexpected number of rows in panel forecast.",
            )
        result = result.copy()
        result.insert(
            0,
            request.item_id_col,
            [
                item_id
                for item_id in item_ids
                for _ in range(request.forecast_horizon)
            ],
        )

    return ForecastResponse(
        predictions=json.loads(result.to_json(orient="records", date_format="iso"))
    )


@app.post(
    "/forecast",
    response_model=ForecastResponse,
    tags=["Forecasts"],
    summary="Forecast from JSON observations (legacy contract)",
)
def forecast(request: ForecastRequest) -> ForecastResponse:
    """Generate a singular-target point forecast and prediction interval."""
    return _run_forecast(request)


@app.post(
    "/v2/forecast",
    response_model=V2ForecastResponse,
    tags=["Forecasts"],
    summary="Forecast one or more targets through the generic API",
    description=(
        "Use `target_cols` for related variables belonging to one task and "
        "`item_id_col` for multiple tasks/items. Chronos 2 forecasts multiple "
        "targets jointly; it does not loop over targets independently."
    ),
)
def forecast_v2(request: V2ForecastRequest) -> V2ForecastResponse:
    """Generate a stable long-format forecast response."""
    required = {request.datetime_col, *request.target_cols}
    if request.item_id_col:
        required.add(request.item_id_col)
    data = _normalize_timestamps(
        _as_dataframe(request.data, "data", required), "data", request.datetime_col
    )
    future = _normalize_timestamps(
        _as_dataframe(
            request.future_data,
            "future_data",
            {request.datetime_col, *({request.item_id_col} if request.item_id_col else set())},
        ),
        "future_data",
        request.datetime_col,
    )

    try:
        with _forecast_lock:
            result = forecast_engine.forecast(
                data=data,
                target_cols=request.target_cols,
                forecast_horizon=request.forecast_horizon,
                datetime_col=request.datetime_col,
                item_id_col=request.item_id_col,
                frequency=request.frequency,
                model=request.model,
                future_data=future,
                quantile_levels=request.quantile_levels,
                batch_size=request.batch_size,
                context_length=request.context_length,
                cross_learning=request.cross_learning,
            )
    except Exception as exc:  # noqa: BLE001 - converted at the transport boundary
        _raise_forecast_error(exc)

    return V2ForecastResponse(
        predictions=[V2Prediction(**record) for record in result.to_records()]
    )


@app.post(
    "/forecast/csv",
    response_model=ForecastResponse,
    tags=["Forecasts"],
    summary="Upload a CSV and generate a legacy forecast",
    description=(
        "Upload historical target data and, for Chronos 2, optional past and "
        "future covariate CSVs."
    ),
)
def forecast_csv(
    file: UploadFile = File(description="CSV containing timestamps and target values"),
    past_covariates_file: UploadFile | None = File(
        None, description="Optional CSV with historical Chronos 2 covariates"
    ),
    future_covariates_file: UploadFile | None = File(
        None, description="Optional CSV with known future Chronos 2 covariates"
    ),
    datetime_col: str = Form("date", description="Timestamp column name"),
    target_col: str = Form("target", description="Value column name"),
    item_id_col: str = Form(
        "", description="Series ID column; leave blank for one series"
    ),
    forecast_horizon: int = Form(24, gt=0, description="Future steps to predict"),
    frequency: str = Form("h", description="Pandas frequency, for example h or D"),
    engine: Literal["chronos", "chronos2"] = Form("chronos2"),
    random_state: int = Form(42, description="Compatibility seed field"),
) -> ForecastResponse:
    """Convert an uploaded CSV into the regular legacy forecast request."""
    return _run_forecast_from_csv(
        file,
        past_covariates_file,
        future_covariates_file,
        datetime_col,
        target_col,
        item_id_col,
        forecast_horizon,
        frequency,
        engine,
        random_state,
    )


def _run_forecast_from_csv(
    file: UploadFile,
    past_covariates_file: UploadFile | None,
    future_covariates_file: UploadFile | None,
    datetime_col: str,
    target_col: str,
    item_id_col: str,
    forecast_horizon: int,
    frequency: str,
    engine: Literal["chronos", "chronos2"],
    random_state: int,
) -> ForecastResponse:
    data = _read_csv(file, "file")
    past_covariates = _read_csv(past_covariates_file, "past_covariates_file")
    future_covariates = _read_csv(future_covariates_file, "future_covariates_file")

    return _run_forecast(
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


saas_router.add_api_route(
    "/forecast",
    forecast,
    methods=["POST"],
    response_model=ForecastResponse,
    summary="Authenticated legacy forecast from JSON observations",
    operation_id="saas_forecast",
)
saas_router.add_api_route(
    "/forecast/csv",
    forecast_csv,
    methods=["POST"],
    response_model=ForecastResponse,
    summary="Authenticated legacy CSV forecast",
    operation_id="saas_forecast_csv",
)
app.include_router(saas_router)


def _read_csv(upload: UploadFile | None, name: str) -> list[dict[str, Any]] | None:
    if upload is None:
        return None

    try:
        return pd.read_csv(upload.file).to_dict(orient="records")
    except (UnicodeDecodeError, pd.errors.EmptyDataError, pd.errors.ParserError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"Invalid {name}: {exc}") from exc


if __name__ == "__main__":
    uvicorn.run(
        app,
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
    )
