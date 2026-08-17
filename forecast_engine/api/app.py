"""FastAPI transport for the Forecast Engine package."""

from __future__ import annotations

import logging
import os
from importlib.metadata import version
from secrets import compare_digest
from threading import Lock
from typing import Annotated, Any

import pandas as pd
from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from forecast_engine import ForecastEngine
from forecast_engine.errors import ForecastValidationError

from .schemas import (
    ForecastRequest,
    ForecastResponse,
    ModelCapabilities,
    ModelsResponse,
    Prediction,
)


logger = logging.getLogger(__name__)
PACKAGE_VERSION = version("forecast-engine")

forecast_service = ForecastEngine(
    device=os.getenv("FORECAST_DEVICE"),
    dtype=os.getenv("FORECAST_DTYPE"),
    revision=os.getenv("FORECAST_MODEL_REVISION"),
)
_forecast_lock = Lock()
_bearer = HTTPBearer(auto_error=False)


def require_auth(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(_bearer)
    ],
) -> None:
    """Require the configured server-to-server bearer token."""
    expected_token = os.getenv("SAAS_API_TOKEN")
    if not expected_token:
        raise HTTPException(
            status_code=503,
            detail="Bearer authentication is not configured.",
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


app = FastAPI(
    title="Forecast Engine",
    summary="Time-series forecasting with official Amazon Chronos pipelines",
    description=(
        "Generate forecasts through the reusable Forecast Engine Python core. "
        "The authenticated `POST /forecast` endpoint accepts structured records "
        "and returns a stable long-format response."
    ),
    version=PACKAGE_VERSION,
    openapi_tags=[
        {
            "name": "Forecasts",
            "description": "Authenticated structured time-series forecasting.",
        },
        {
            "name": "Models",
            "description": "Configured model names and capabilities.",
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
        "forecast_engine_version": PACKAGE_VERSION,
        "chronos_forecasting_version": version("chronos-forecasting"),
        "loaded_models": forecast_service.pipeline_manager.loaded_models,
        "cached_pipelines": forecast_service.pipeline_manager.cached_pipeline_count,
    }


@app.get(
    "/models",
    response_model=ModelsResponse,
    tags=["Models"],
    summary="List configured forecasting models",
)
def models() -> ModelsResponse:
    """List model capabilities without loading model weights."""
    return ModelsResponse(
        models=[
            ModelCapabilities(
                id=spec.name,
                model_id=spec.model_id,
                multivariate=spec.multivariate,
                covariates=spec.covariates,
                cross_learning=spec.cross_learning,
                panel=spec.panel,
                context_length=spec.context_length,
            )
            for spec in forecast_service.registry.specs()
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


def _raise_forecast_error(exc: Exception) -> None:
    if isinstance(exc, (ForecastValidationError, KeyError, TypeError, ValueError)):
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    logger.exception("Forecast inference failed")
    raise HTTPException(status_code=500, detail="Forecast inference failed.") from exc


def run_forecast(request: ForecastRequest) -> ForecastResponse:
    """Convert the HTTP request and call the reusable Python core once."""
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
            {
                request.datetime_col,
                *({request.item_id_col} if request.item_id_col else set()),
            },
        ),
        "future_data",
        request.datetime_col,
    )

    try:
        with _forecast_lock:
            result = forecast_service.forecast(
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

    return ForecastResponse(
        predictions=[Prediction(**record) for record in result.to_records()]
    )


@app.post(
    "/forecast",
    response_model=ForecastResponse,
    tags=["Forecasts"],
    summary="Forecast structured time-series records",
    description=(
        "Use `target_cols` for related variables in one task and `item_id_col` "
        "for multiple tasks/items. Chronos 2 forecasts multiple targets jointly "
        "in one native multivariate call. Response timestamps are UTC ISO 8601 "
        "values with a `Z` suffix and can be reused directly as input."
    ),
    dependencies=[Depends(require_auth)],
)
def forecast(request: ForecastRequest) -> ForecastResponse:
    """Generate a forecast through the authenticated public contract."""
    return run_forecast(request)
