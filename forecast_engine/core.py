"""Reusable Forecast Engine core built on the official Chronos pipelines."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

import numpy as np
import pandas as pd
from chronos.df_utils import make_future_df, validate_and_normalize_df
from pandas.api.types import is_bool_dtype, is_numeric_dtype

from .errors import ForecastInferenceError, ForecastValidationError
from .models import ModelRegistry, ModelSpec
from .pipeline import PipelineManager


DEFAULT_QUANTILE_LEVELS: tuple[float, ...] = (0.1, 0.5, 0.9)
_INTERNAL_ITEM_PREFIX = "__forecast_engine_item_id__"


@dataclass(frozen=True)
class ForecastResult:
    """Canonical long-format result returned by the Python forecasting API."""

    predictions: pd.DataFrame
    quantile_levels: tuple[float, ...]

    def to_records(self) -> list[dict[str, Any]]:
        """Return JSON-friendly long-format records for transport adapters."""
        records: list[dict[str, Any]] = []
        quantile_columns = {level: f"q_{level}" for level in self.quantile_levels}
        for row in self.predictions.to_dict(orient="records"):
            timestamp = pd.Timestamp(row["timestamp"])
            if timestamp.tzinfo is None:
                timestamp = timestamp.tz_localize("UTC")
            else:
                timestamp = timestamp.tz_convert("UTC")
            item_id = row["item_id"]
            if item_id is not None and pd.isna(item_id):
                item_id = None
            if hasattr(item_id, "item"):
                item_id = item_id.item()

            quantiles = {
                str(level): float(row[column])
                for level, column in quantile_columns.items()
            }
            records.append(
                {
                    "timestamp": timestamp.isoformat().replace("+00:00", "Z"),
                    "item_id": item_id,
                    "target_name": str(row["target_name"]),
                    "prediction": float(row["prediction"]),
                    "quantiles": quantiles,
                }
            )
        return records

    def to_legacy_dataframe(
        self,
        *,
        datetime_col: str,
        target_col: str,
        item_id_col: str | None,
    ) -> pd.DataFrame:
        """Format this result using the historical singular-target columns."""
        return _legacy_dataframe(
            self,
            datetime_col=datetime_col,
            target_col=target_col,
            item_id_col=item_id_col,
        )


class ForecastEngine:
    """Own application-level validation, normalization, and Chronos inference."""

    def __init__(
        self,
        *,
        registry: ModelRegistry | None = None,
        pipeline_manager: PipelineManager | None = None,
        device: str | None = None,
        dtype: str | None = None,
        revision: str | None = None,
    ) -> None:
        self.registry = registry or ModelRegistry()
        self.pipeline_manager = pipeline_manager or PipelineManager(
            device=device,
            dtype=dtype,
            revision=revision,
        )

    def forecast(
        self,
        *,
        data: pd.DataFrame,
        target_cols: Sequence[str],
        forecast_horizon: int,
        datetime_col: str = "date",
        item_id_col: str | None = None,
        frequency: str = "h",
        model: str = "chronos2",
        future_data: pd.DataFrame | None = None,
        quantile_levels: Sequence[float] = DEFAULT_QUANTILE_LEVELS,
        batch_size: int = 256,
        context_length: int | None = None,
        cross_learning: bool = False,
    ) -> ForecastResult:
        """Forecast one or more targets for one or more items in one model call."""
        spec = self.registry.get(model)
        targets = self._validate_request_arguments(
            data=data,
            target_cols=target_cols,
            forecast_horizon=forecast_horizon,
            datetime_col=datetime_col,
            frequency=frequency,
            quantile_levels=quantile_levels,
            batch_size=batch_size,
            context_length=context_length,
        )

        context, future, internal_item_col = self._prepare_frames(
            data=data,
            future_data=future_data,
            target_cols=targets,
            forecast_horizon=forecast_horizon,
            datetime_col=datetime_col,
            item_id_col=item_id_col,
            frequency=frequency,
        )
        self._validate_capabilities(
            spec=spec,
            target_cols=targets,
            context=context,
            future=future,
            internal_item_col=internal_item_col,
            datetime_col=datetime_col,
            cross_learning=cross_learning,
            context_length=context_length,
        )

        quantiles = tuple(float(level) for level in quantile_levels)
        try:
            with self.pipeline_manager.pipeline(spec) as pipeline:
                kwargs: dict[str, Any] = {
                    "id_column": internal_item_col,
                    "timestamp_column": datetime_col,
                    "prediction_length": forecast_horizon,
                    "quantile_levels": list(quantiles),
                    "batch_size": batch_size,
                    "validate_inputs": True,
                    "freq": frequency,
                }
                if spec.family == "chronos2":
                    kwargs.update(
                        {
                            "future_df": future,
                            "target": targets,
                            "context_length": context_length,
                            "cross_learning": cross_learning,
                        }
                    )
                else:
                    kwargs["target"] = targets[0]

                raw_result = pipeline.predict_df(context, **kwargs)
        except (KeyError, TypeError, ValueError) as exc:
            raise ForecastValidationError(str(exc)) from exc

        return self._normalize_result(
            raw_result=raw_result,
            quantile_levels=quantiles,
            target_cols=targets,
            forecast_horizon=forecast_horizon,
            item_id_col=item_id_col,
            internal_item_col=internal_item_col,
            datetime_col=datetime_col,
        )

    def forecast_legacy(
        self,
        *,
        data: pd.DataFrame,
        datetime_col: str,
        target_col: str,
        item_id_col: str | None,
        frequency: str,
        forecast_horizon: int,
        engine: str,
        past_covariates: pd.DataFrame | None = None,
        future_covariates: pd.DataFrame | None = None,
    ) -> pd.DataFrame:
        """Adapt the historical singular-target contract onto :meth:`forecast`."""
        normalized_data, normalized_future = self._merge_legacy_covariates(
            data=data,
            past_covariates=past_covariates,
            future_covariates=future_covariates,
            datetime_col=datetime_col,
            target_col=target_col,
            item_id_col=item_id_col,
        )
        engine_key = engine.lower()
        if engine_key == "chronos2":
            model = "chronos2"
        elif engine_key == "chronos":
            model = "chronos-bolt-base"
        else:
            raise ForecastValidationError(f"Unknown engine: {engine}")

        result = self.forecast(
            data=normalized_data,
            target_cols=[target_col],
            forecast_horizon=forecast_horizon,
            datetime_col=datetime_col,
            item_id_col=item_id_col,
            frequency=frequency,
            model=model,
            future_data=normalized_future,
            quantile_levels=DEFAULT_QUANTILE_LEVELS,
        )
        return result.to_legacy_dataframe(
            datetime_col=datetime_col,
            target_col=target_col,
            item_id_col=item_id_col,
        )

    def _validate_request_arguments(
        self,
        *,
        data: pd.DataFrame,
        target_cols: Sequence[str],
        forecast_horizon: int,
        datetime_col: str,
        frequency: str,
        quantile_levels: Sequence[float],
        batch_size: int,
        context_length: int | None,
    ) -> list[str]:
        if not isinstance(data, pd.DataFrame):
            raise ForecastValidationError("data must be a pandas DataFrame")
        if data.empty:
            raise ForecastValidationError("data must contain at least one row")
        if data.columns.duplicated().any():
            raise ForecastValidationError("data contains duplicate column names")
        if not isinstance(target_cols, Sequence) or isinstance(target_cols, (str, bytes)):
            raise ForecastValidationError("target_cols must be a list of column names")
        targets = list(target_cols)
        if not targets:
            raise ForecastValidationError("target_cols must contain at least one column")
        if any(not isinstance(target, str) or not target for target in targets):
            raise ForecastValidationError("target_cols must contain non-empty strings")
        if len(set(targets)) != len(targets):
            raise ForecastValidationError("target_cols must not contain duplicates")
        if not isinstance(forecast_horizon, int) or isinstance(forecast_horizon, bool):
            raise ForecastValidationError("forecast_horizon must be a positive integer")
        if forecast_horizon <= 0:
            raise ForecastValidationError("forecast_horizon must be a positive integer")
        if not isinstance(datetime_col, str) or not datetime_col:
            raise ForecastValidationError("datetime_col must be a non-empty string")
        if not isinstance(frequency, str) or not frequency.strip():
            raise ForecastValidationError("frequency must be a non-empty frequency string")
        try:
            pd.tseries.frequencies.to_offset(frequency)
        except (TypeError, ValueError) as exc:
            raise ForecastValidationError(f"Invalid frequency '{frequency}': {exc}") from exc
        if not isinstance(batch_size, int) or isinstance(batch_size, bool) or batch_size <= 0:
            raise ForecastValidationError("batch_size must be a positive integer")
        if context_length is not None and (
            not isinstance(context_length, int)
            or isinstance(context_length, bool)
            or context_length <= 0
        ):
            raise ForecastValidationError("context_length must be a positive integer")
        try:
            levels = list(quantile_levels)
        except TypeError as exc:
            raise ForecastValidationError(
                "quantile_levels must be a sequence of numbers"
            ) from exc
        if not levels:
            raise ForecastValidationError("quantile_levels must contain at least one level")
        if any(not isinstance(level, (float, int)) or isinstance(level, bool) for level in levels):
            raise ForecastValidationError("quantile_levels must contain numbers")
        if any(not 0.0 < float(level) < 1.0 for level in levels):
            raise ForecastValidationError("quantile_levels must be strictly between 0 and 1")
        if len({float(level) for level in levels}) != len(levels):
            raise ForecastValidationError("quantile_levels must not contain duplicates")
        return targets

    def _prepare_frames(
        self,
        *,
        data: pd.DataFrame,
        future_data: pd.DataFrame | None,
        target_cols: list[str],
        forecast_horizon: int,
        datetime_col: str,
        item_id_col: str | None,
        frequency: str,
    ) -> tuple[pd.DataFrame, pd.DataFrame | None, str]:
        context = self._normalize_timestamps(data, "data", datetime_col)
        required = {datetime_col, *target_cols}
        if item_id_col:
            required.add(item_id_col)
        self._require_columns(context, required, "data")

        for target in target_cols:
            series = context[target]
            if is_bool_dtype(series) or not is_numeric_dtype(series):
                raise ForecastValidationError(
                    f"Target column '{target}' must be numeric"
                )
            if series.isna().any():
                raise ForecastValidationError(
                    f"Target column '{target}' contains missing values"
                )

        internal_item_col = item_id_col or self._new_internal_item_col(context, future_data)
        if item_id_col:
            if context[item_id_col].isna().any():
                raise ForecastValidationError(
                    f"Item ID column '{item_id_col}' contains missing values"
                )
        else:
            context[internal_item_col] = 0

        if context.duplicated([internal_item_col, datetime_col]).any():
            raise ForecastValidationError(
                "data contains duplicate timestamps for an item"
            )

        future: pd.DataFrame | None = None
        if future_data is not None:
            future = self._normalize_timestamps(future_data, "future_data", datetime_col)
            future_required = {datetime_col}
            if item_id_col:
                future_required.add(item_id_col)
            self._require_columns(future, future_required, "future_data")
            if future.empty:
                raise ForecastValidationError("future_data must contain at least one row")
            if not item_id_col:
                future[internal_item_col] = 0
            elif future[item_id_col].isna().any():
                raise ForecastValidationError(
                    f"Item ID column '{item_id_col}' contains missing values in future_data"
                )
            if any(target in future.columns for target in target_cols):
                found = [target for target in target_cols if target in future.columns]
                raise ForecastValidationError(
                    f"future_data must not contain target columns: {found}"
                )
            if future.duplicated([internal_item_col, datetime_col]).any():
                raise ForecastValidationError(
                    "future_data contains duplicate timestamps for an item"
                )

            context_columns = set(context.columns)
            invalid_future_columns = set(future.columns) - context_columns
            if invalid_future_columns:
                raise ForecastValidationError(
                    "future_data contains columns absent from data: "
                    + ", ".join(sorted(invalid_future_columns))
                )

            context_items = list(pd.unique(context[internal_item_col]))
            future_items = list(pd.unique(future[internal_item_col]))
            if len(context_items) != len(future_items) or any(
                item not in context_items for item in future_items
            ):
                raise ForecastValidationError(
                    "future_data must contain the same item IDs as data"
                )
            counts = future.groupby(internal_item_col, sort=False).size()
            if (counts != forecast_horizon).any() or len(counts) != len(context_items):
                raise ForecastValidationError(
                    "future_data must contain exactly "
                    f"forecast_horizon={forecast_horizon} rows per item"
                )

        try:
            context, future = validate_and_normalize_df(
                df=context,
                future_df=future,
                target_columns=target_cols,
                prediction_length=forecast_horizon,
                id_column=internal_item_col,
                timestamp_column=datetime_col,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ForecastValidationError(str(exc)) from exc

        if future is not None:
            expected = make_future_df(
                context,
                prediction_length=forecast_horizon,
                freq=frequency,
                id_column=internal_item_col,
                timestamp_column=datetime_col,
            )
            actual_index = pd.MultiIndex.from_frame(
                future[[internal_item_col, datetime_col]]
            )
            expected_index = pd.MultiIndex.from_frame(
                expected[[internal_item_col, datetime_col]]
            )
            if not actual_index.equals(expected_index):
                raise ForecastValidationError(
                    "future_data timestamps do not match the requested frequency "
                    "and forecast horizon"
                )

        return context, future, internal_item_col

    def _validate_capabilities(
        self,
        *,
        spec: ModelSpec,
        target_cols: list[str],
        context: pd.DataFrame,
        future: pd.DataFrame | None,
        internal_item_col: str,
        datetime_col: str,
        cross_learning: bool,
        context_length: int | None,
    ) -> None:
        if len(target_cols) > 1 and not spec.multivariate:
            raise ForecastValidationError(
                f"Model '{spec.alias}' supports univariate forecasting only; "
                "choose chronos2 for multiple target columns."
            )

        historical_covariates = set(context.columns) - {
            internal_item_col,
            datetime_col,
            *target_cols,
        }
        future_covariates = (
            set(future.columns) - {internal_item_col, datetime_col}
            if future is not None
            else set()
        )
        has_covariates = bool(historical_covariates or future_covariates)
        if has_covariates and not spec.covariates:
            raise ForecastValidationError(
                f"Model '{spec.alias}' does not support historical or future covariates"
            )
        if future is not None and not spec.covariates:
            raise ForecastValidationError(
                f"Model '{spec.alias}' does not support future_data"
            )
        if cross_learning and not spec.cross_learning:
            raise ForecastValidationError(
                f"Model '{spec.alias}' does not support cross_learning"
            )
        if context_length is not None and not spec.context_length:
            raise ForecastValidationError(
                f"Model '{spec.alias}' does not expose context_length"
            )

    def _normalize_result(
        self,
        *,
        raw_result: Any,
        quantile_levels: tuple[float, ...],
        target_cols: list[str],
        forecast_horizon: int,
        item_id_col: str | None,
        internal_item_col: str,
        datetime_col: str,
    ) -> ForecastResult:
        if not isinstance(raw_result, pd.DataFrame):
            raise ForecastInferenceError("Chronos returned an invalid result type")

        id_column = next(
            (
                column
                for column in (internal_item_col, "item_id", "id")
                if column in raw_result.columns
            ),
            None,
        )
        required = {datetime_col, "target_name", "predictions"}
        missing = required - set(raw_result.columns)
        if missing:
            raise ForecastInferenceError(
                f"Chronos result is missing columns: {sorted(missing)}"
            )
        quantile_columns = {level: str(level) for level in quantile_levels}
        missing_quantiles = [
            str(level)
            for level, column in quantile_columns.items()
            if column not in raw_result.columns
        ]
        if missing_quantiles:
            raise ForecastInferenceError(
                "Chronos result is missing requested quantiles: "
                + ", ".join(missing_quantiles)
            )

        expected_rows = (
            (raw_result[id_column].nunique() if id_column else 1)
            * len(target_cols)
            * forecast_horizon
        )
        if len(raw_result) != expected_rows:
            raise ForecastInferenceError(
                "Chronos returned an unexpected number of forecast rows"
            )

        numeric_columns = ["predictions", *quantile_columns.values()]
        for column in numeric_columns:
            values = pd.to_numeric(raw_result[column], errors="coerce")
            if values.isna().any() or not np.isfinite(values.to_numpy()).all():
                raise ForecastInferenceError(
                    f"Chronos returned invalid numeric values in '{column}'"
                )

        target_names = set(raw_result["target_name"].astype(str))
        if target_names != set(target_cols):
            raise ForecastInferenceError(
                "Chronos returned an incomplete or unknown target set"
            )

        canonical = pd.DataFrame(
            {
                "timestamp": pd.to_datetime(raw_result[datetime_col]),
                "item_id": (
                    raw_result[id_column].tolist()
                    if item_id_col and id_column is not None
                    else [None] * len(raw_result)
                ),
                "target_name": raw_result["target_name"].astype(str).tolist(),
                "prediction": pd.to_numeric(raw_result["predictions"]).astype(float),
            }
        )
        for level, source_column in quantile_columns.items():
            canonical[f"q_{level}"] = pd.to_numeric(
                raw_result[source_column]
            ).astype(float)

        return ForecastResult(
            predictions=canonical,
            quantile_levels=quantile_levels,
        )

    @staticmethod
    def _require_columns(
        frame: pd.DataFrame, required: set[str], name: str
    ) -> None:
        missing = required - set(frame.columns)
        if missing:
            raise ForecastValidationError(
                f"{name} is missing columns: {', '.join(sorted(missing))}"
            )

    @staticmethod
    def _normalize_timestamps(
        frame: pd.DataFrame, name: str, datetime_col: str
    ) -> pd.DataFrame:
        if not isinstance(frame, pd.DataFrame):
            raise ForecastValidationError(f"{name} must be a pandas DataFrame")
        if frame.empty:
            raise ForecastValidationError(f"{name} must contain at least one row")
        if frame.columns.duplicated().any():
            raise ForecastValidationError(f"{name} contains duplicate column names")
        if datetime_col not in frame.columns:
            raise ForecastValidationError(
                f"{name} is missing datetime column '{datetime_col}'"
            )
        try:
            timestamps = pd.to_datetime(frame[datetime_col], utc=True, errors="raise")
        except (TypeError, ValueError) as exc:
            raise ForecastValidationError(
                f"{name} has invalid timestamps in column '{datetime_col}': {exc}"
            ) from exc
        if timestamps.isna().any():
            raise ForecastValidationError(
                f"{name} has missing timestamps in column '{datetime_col}'"
            )
        normalized = frame.copy()
        normalized[datetime_col] = timestamps.dt.tz_localize(None)
        return normalized

    @staticmethod
    def _new_internal_item_col(
        data: pd.DataFrame, future_data: pd.DataFrame | None
    ) -> str:
        columns = set(data.columns)
        if future_data is not None:
            columns.update(future_data.columns)
        candidate = _INTERNAL_ITEM_PREFIX
        index = 1
        while candidate in columns:
            candidate = f"{_INTERNAL_ITEM_PREFIX}{index}"
            index += 1
        return candidate

    def _merge_legacy_covariates(
        self,
        *,
        data: pd.DataFrame,
        past_covariates: pd.DataFrame | None,
        future_covariates: pd.DataFrame | None,
        datetime_col: str,
        target_col: str,
        item_id_col: str | None,
    ) -> tuple[pd.DataFrame, pd.DataFrame | None]:
        context = self._normalize_timestamps(data, "data", datetime_col)
        past = (
            self._normalize_timestamps(past_covariates, "past_covariates", datetime_col)
            if past_covariates is not None
            else None
        )
        future = (
            self._normalize_timestamps(
                future_covariates, "future_covariates", datetime_col
            )
            if future_covariates is not None
            else None
        )

        if past is not None or future is not None:
            if item_id_col:
                for name, frame in (
                    ("past_covariates", past),
                    ("future_covariates", future),
                ):
                    if frame is not None and item_id_col not in frame.columns:
                        raise ForecastValidationError(
                            f"{name} is missing item ID column '{item_id_col}'"
                        )

            join_columns = [datetime_col]
            internal_item_col: str | None = None
            if item_id_col:
                join_columns.append(item_id_col)
            else:
                potential_future = future if future is not None else past
                internal_item_col = self._new_internal_item_col(
                    context, potential_future
                )
                context[internal_item_col] = 0
                for frame in (past, future):
                    if frame is not None:
                        frame[internal_item_col] = 0
                join_columns.append(internal_item_col)

            for name, frame in (("past_covariates", past), ("future_covariates", future)):
                if frame is None:
                    continue
                if frame.duplicated(join_columns).any():
                    raise ForecastValidationError(
                        f"{name} contains duplicate timestamps for an item"
                    )
                forbidden = set(frame.columns) & {target_col}
                if forbidden:
                    raise ForecastValidationError(
                        f"{name} must not contain target columns: {sorted(forbidden)}"
                    )

            if past is not None:
                covariate_columns = set(past.columns) - set(join_columns)
                collisions = covariate_columns & set(context.columns)
                if collisions:
                    raise ForecastValidationError(
                        "past_covariates contains columns already present in data: "
                        + ", ".join(sorted(collisions))
                    )
                context = context.merge(
                    past,
                    on=join_columns,
                    how="left",
                    validate="one_to_one",
                )

            if internal_item_col is not None:
                context = context.drop(columns=[internal_item_col])
                if future is not None:
                    future = future.drop(columns=[internal_item_col])

        return context, future


def _legacy_dataframe(
    result: ForecastResult,
    *,
    datetime_col: str,
    target_col: str,
    item_id_col: str | None,
) -> pd.DataFrame:
    """Format the canonical result using the historical response column names."""
    prediction = result.predictions
    required_quantiles = {level: f"q_{level}" for level in DEFAULT_QUANTILE_LEVELS}
    missing = [
        str(level)
        for level, column in required_quantiles.items()
        if column not in prediction.columns
    ]
    if missing:
        raise ForecastInferenceError(
            "Legacy output requires quantiles: " + ", ".join(missing)
        )

    output = pd.DataFrame(
        {
            datetime_col: prediction["timestamp"],
            f"{target_col}_predicted": prediction["prediction"],
            "lower_bound": prediction[required_quantiles[0.1]],
            "upper_bound": prediction[required_quantiles[0.9]],
        }
    )
    if item_id_col:
        output.insert(0, item_id_col, prediction["item_id"])
    return output
