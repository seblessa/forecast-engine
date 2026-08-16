"""Errors raised by the Forecast Engine Python core."""

from __future__ import annotations


class ForecastEngineError(Exception):
    """Base class for errors raised by the forecasting core."""


class ForecastValidationError(ForecastEngineError, ValueError):
    """The caller supplied data or configuration the selected model cannot use."""


class ForecastInferenceError(ForecastEngineError):
    """The model returned an invalid result or failed during inference."""
