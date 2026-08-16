"""Configured model aliases and their supported forecasting capabilities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .errors import ForecastValidationError


@dataclass(frozen=True)
class ModelSpec:
    """A server-controlled model alias and the capabilities it exposes."""

    alias: str
    model_id: str
    family: str
    multivariate: bool
    covariates: bool
    cross_learning: bool
    panel: bool = True
    context_length: bool = False
    legacy_aliases: tuple[str, ...] = ()


DEFAULT_MODEL_SPECS: tuple[ModelSpec, ...] = (
    ModelSpec(
        alias="chronos2",
        model_id="amazon/chronos-2",
        family="chronos2",
        multivariate=True,
        covariates=True,
        cross_learning=True,
        panel=True,
        context_length=True,
    ),
    ModelSpec(
        alias="chronos-bolt-base",
        model_id="amazon/chronos-bolt-base",
        family="chronos-bolt",
        multivariate=False,
        covariates=False,
        cross_learning=False,
        panel=True,
        context_length=False,
        legacy_aliases=("chronos",),
    ),
)


class ModelRegistry:
    """Resolve client-facing aliases without allowing arbitrary model IDs."""

    def __init__(self, specs: Iterable[ModelSpec] = DEFAULT_MODEL_SPECS) -> None:
        canonical: dict[str, ModelSpec] = {}
        aliases: dict[str, ModelSpec] = {}
        for spec in specs:
            key = spec.alias.lower()
            if key in canonical or key in aliases:
                raise ValueError(f"Duplicate model alias: {spec.alias}")
            canonical[key] = spec
            for legacy_alias in spec.legacy_aliases:
                legacy_key = legacy_alias.lower()
                if legacy_key in canonical or legacy_key in aliases:
                    raise ValueError(f"Duplicate model alias: {legacy_alias}")
                aliases[legacy_key] = spec

        self._canonical = canonical
        self._aliases = aliases

    def get(self, alias: str) -> ModelSpec:
        """Return a configured model or raise a request-level error."""
        if not isinstance(alias, str) or not alias.strip():
            raise ForecastValidationError("model must be a configured model alias")

        spec = self._canonical.get(alias.lower()) or self._aliases.get(alias.lower())
        if spec is None:
            available = ", ".join(self.aliases())
            raise ForecastValidationError(
                f"Unknown model alias '{alias}'. Available models: {available}."
            )
        return spec

    def aliases(self) -> tuple[str, ...]:
        """Return canonical aliases in registry order."""
        return tuple(spec.alias for spec in self._canonical.values())

    def specs(self) -> tuple[ModelSpec, ...]:
        """Return canonical model specifications in registry order."""
        return tuple(self._canonical.values())
