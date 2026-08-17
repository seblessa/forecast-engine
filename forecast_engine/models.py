"""Configured models and their supported forecasting capabilities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .errors import ForecastValidationError


@dataclass(frozen=True)
class ModelSpec:
    """A server-controlled model name and the capabilities it exposes."""

    name: str
    model_id: str
    family: str
    multivariate: bool
    covariates: bool
    cross_learning: bool
    panel: bool = True
    context_length: bool = False


DEFAULT_MODEL_SPECS: tuple[ModelSpec, ...] = (
    ModelSpec(
        name="chronos2",
        model_id="amazon/chronos-2",
        family="chronos2",
        multivariate=True,
        covariates=True,
        cross_learning=True,
        panel=True,
        context_length=True,
    ),
    ModelSpec(
        name="chronos-bolt-base",
        model_id="amazon/chronos-bolt-base",
        family="chronos-bolt",
        multivariate=False,
        covariates=False,
        cross_learning=False,
        panel=True,
        context_length=False,
    ),
)


class ModelRegistry:
    """Resolve configured model names without allowing arbitrary model IDs."""

    def __init__(self, specs: Iterable[ModelSpec] = DEFAULT_MODEL_SPECS) -> None:
        canonical: dict[str, ModelSpec] = {}
        for spec in specs:
            key = spec.name.lower()
            if key in canonical:
                raise ValueError(f"Duplicate model name: {spec.name}")
            canonical[key] = spec

        self._canonical = canonical

    def get(self, model_name: str) -> ModelSpec:
        """Return a configured model or raise a request-level error."""
        if not isinstance(model_name, str) or not model_name.strip():
            raise ForecastValidationError("model must be a configured model name")

        spec = self._canonical.get(model_name.lower())
        if spec is None:
            available = ", ".join(self.names())
            raise ForecastValidationError(
                f"Unknown model '{model_name}'. Available models: {available}."
            )
        return spec

    def names(self) -> tuple[str, ...]:
        """Return configured model names in registry order."""
        return tuple(spec.name for spec in self._canonical.values())

    def specs(self) -> tuple[ModelSpec, ...]:
        """Return canonical model specifications in registry order."""
        return tuple(self._canonical.values())
