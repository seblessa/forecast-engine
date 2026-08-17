"""Pydantic schemas for the Forecast Engine HTTP transport."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ForecastRequest(BaseModel):
    """The single structured forecasting request contract."""

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


class Prediction(BaseModel):
    timestamp: str
    item_id: Any | None = None
    target_name: str
    prediction: float
    quantiles: dict[str, float]


class ForecastResponse(BaseModel):
    predictions: list[Prediction]


class ModelCapabilities(BaseModel):
    id: str
    model_id: str
    multivariate: bool
    covariates: bool
    cross_learning: bool
    panel: bool
    context_length: bool


class ModelsResponse(BaseModel):
    models: list[ModelCapabilities]
