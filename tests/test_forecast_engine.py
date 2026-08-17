from __future__ import annotations

from collections.abc import Sequence

import pandas as pd
import pytest

from forecast_engine import ForecastEngine, PipelineManager
from forecast_engine.errors import ForecastValidationError


class RecordingPipeline:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def predict_df(self, frame: pd.DataFrame, **kwargs) -> pd.DataFrame:
        self.calls.append({"frame": frame.copy(), **kwargs})
        target = kwargs["target"]
        targets = [target] if isinstance(target, str) else list(target)
        id_column = kwargs["id_column"]
        timestamp_column = kwargs["timestamp_column"]
        horizon = kwargs["prediction_length"]
        frequency = kwargs["freq"]
        quantiles = kwargs["quantile_levels"]

        rows: list[dict] = []
        for item_id, item_frame in frame.groupby(id_column, sort=False):
            last_timestamp = item_frame[timestamp_column].max()
            timestamps = pd.date_range(
                last_timestamp,
                periods=horizon + 1,
                freq=frequency,
            )[1:]
            for target_index, target_name in enumerate(targets):
                for step, timestamp in enumerate(timestamps, start=1):
                    row = {
                        id_column: item_id,
                        timestamp_column: timestamp,
                        "target_name": target_name,
                        "predictions": float(target_index + step),
                    }
                    row.update({str(level): float(level) for level in quantiles})
                    rows.append(row)
        return pd.DataFrame(rows)


def make_engine() -> tuple[ForecastEngine, RecordingPipeline, list[dict]]:
    pipeline = RecordingPipeline()
    loads: list[dict] = []

    def loader(model_id: str, **kwargs):
        loads.append({"model_id": model_id, **kwargs})
        return pipeline

    manager = PipelineManager(device="cpu", dtype="float32", loader=loader)
    return ForecastEngine(pipeline_manager=manager), pipeline, loads


def make_data(
    targets: Sequence[str] = ("sales",),
    items: Sequence[str | None] = (None,),
) -> pd.DataFrame:
    rows = []
    for item in items:
        for step in range(3):
            row = {
                "date": f"2026-01-01T0{step}:00:00Z",
            }
            if item is not None:
                row["store"] = item
            for target_index, target in enumerate(targets):
                row[target] = float(step + target_index + 1)
            rows.append(row)
    return pd.DataFrame(rows)


def test_python_api_supports_one_target_and_forwards_request_options():
    engine, pipeline, loads = make_engine()

    result = engine.forecast(
        data=make_data(),
        target_cols=["sales"],
        forecast_horizon=2,
        datetime_col="date",
        frequency="h",
        quantile_levels=[0.2, 0.5, 0.8],
        batch_size=7,
        context_length=32,
    )

    assert len(result.predictions) == 2
    assert result.to_records()[0]["quantiles"] == {"0.2": 0.2, "0.5": 0.5, "0.8": 0.8}
    assert len(loads) == 1
    call = pipeline.calls[0]
    assert call["target"] == ["sales"]
    assert call["batch_size"] == 7
    assert call["context_length"] == 32
    assert call["freq"] == "h"


def test_to_records_serializes_utc_explicitly():
    engine, _, _ = make_engine()

    result = engine.forecast(
        data=make_data(targets=["dx", "dy"]),
        target_cols=["dx", "dy"],
        forecast_horizon=1,
        frequency="h",
    )

    records = result.to_records()
    assert {record["timestamp"] for record in records} == {
        "2026-01-01T03:00:00Z"
    }


def test_timestamp_round_trip_is_accepted_without_manual_timezone_changes():
    engine, _, _ = make_engine()
    context = make_data(targets=["dx", "dy"])

    first = engine.forecast(
        data=context,
        target_cols=["dx", "dy"],
        forecast_horizon=1,
        frequency="h",
    )
    first_records = first.to_records()
    returned_timestamp = first_records[0]["timestamp"]
    predictions = {
        record["target_name"]: record["prediction"] for record in first_records
    }
    next_context = pd.concat(
        [
            context,
            pd.DataFrame(
                [
                    {
                        "date": returned_timestamp,
                        "dx": predictions["dx"],
                        "dy": predictions["dy"],
                    }
                ]
            ),
        ],
        ignore_index=True,
    )

    assert returned_timestamp == "2026-01-01T03:00:00Z"
    second = engine.forecast(
        data=next_context,
        target_cols=["dx", "dy"],
        forecast_horizon=1,
        frequency="h",
    )

    assert len(second.to_records()) == 2
    assert {record["target_name"] for record in second.to_records()} == {"dx", "dy"}


def test_multivariate_targets_are_sent_in_one_native_call():
    targets = [f"target_{index}" for index in range(40)]
    engine, pipeline, _ = make_engine()

    result = engine.forecast(
        data=make_data(targets=targets),
        target_cols=targets,
        forecast_horizon=1,
    )

    assert len(pipeline.calls) == 1
    assert pipeline.calls[0]["target"] == targets
    assert set(result.predictions["target_name"]) == set(targets)


def test_multiple_items_and_targets_keep_their_distinction():
    engine, _, _ = make_engine()
    result = engine.forecast(
        data=make_data(targets=["dx", "dy"], items=["A", "B"]),
        target_cols=["dx", "dy"],
        forecast_horizon=2,
        item_id_col="store",
    )

    assert len(result.predictions) == 8
    assert set(result.predictions["item_id"]) == {"A", "B"}
    assert set(result.predictions["target_name"]) == {"dx", "dy"}


def test_historical_and_future_data_use_the_dataframe_interface():
    engine, pipeline, _ = make_engine()
    data = make_data()
    data["temperature"] = [10.0, 11.0, 12.0]
    future = pd.DataFrame(
        {
            "date": ["2026-01-01T03:00:00Z", "2026-01-01T04:00:00Z"],
            "temperature": [13.0, 14.0],
        }
    )

    engine.forecast(
        data=data,
        target_cols=["sales"],
        forecast_horizon=2,
        future_data=future,
        cross_learning=True,
    )

    call = pipeline.calls[0]
    assert "temperature" in call["frame"].columns
    assert call["future_df"]["temperature"].tolist() == [13.0, 14.0]
    assert call["cross_learning"] is True


def test_pipeline_cache_is_reused_for_horizon_and_target_changes():
    engine, pipeline, loads = make_engine()
    engine.forecast(
        data=make_data(targets=["sales"]),
        target_cols=["sales"],
        forecast_horizon=1,
    )
    engine.forecast(
        data=make_data(targets=["sales", "returns"]),
        target_cols=["sales", "returns"],
        forecast_horizon=3,
    )

    assert len(loads) == 1
    assert len(pipeline.calls) == 2


def test_timezone_aware_inputs_are_normalized_to_utc_naive():
    engine, pipeline, _ = make_engine()
    data = pd.DataFrame(
        {
            "date": [
                "2026-03-30T00:00:00+00:00",
                "2026-03-30T02:00:00+01:00",
                "2026-03-30T03:00:00+01:00",
            ],
            "sales": [1.0, 2.0, 3.0],
        }
    )

    engine.forecast(data=data, target_cols=["sales"], forecast_horizon=1)

    received = pipeline.calls[0]["frame"]["date"]
    assert received.tolist() == [
        pd.Timestamp("2026-03-30T00:00:00"),
        pd.Timestamp("2026-03-30T01:00:00"),
        pd.Timestamp("2026-03-30T02:00:00"),
    ]
    assert received.dt.tz is None


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"target_cols": []}, "target_cols"),
        ({"target_cols": ["sales", "sales"]}, "duplicates"),
        ({"target_cols": ["missing"]}, "missing"),
        ({"forecast_horizon": 0}, "positive"),
        ({"target_cols": ["sales"], "frequency": "not-a-frequency"}, "frequency"),
        ({"target_cols": ["sales"], "quantile_levels": [0.0, 0.5]}, "strictly"),
    ],
)
def test_invalid_requests_fail_with_actionable_validation_errors(kwargs, message):
    engine, _, _ = make_engine()
    base = {
        "data": make_data(),
        "target_cols": ["sales"],
        "forecast_horizon": 1,
    }
    base.update(kwargs)

    with pytest.raises(ForecastValidationError, match=message):
        engine.forecast(**base)


def test_invalid_frequency_has_a_sanitized_chained_error():
    engine, _, _ = make_engine()
    invalid_frequency = "not-a-frequency"

    with pytest.raises(ForecastValidationError) as exc_info:
        engine.forecast(
            data=make_data(),
            target_cols=["sales"],
            forecast_horizon=1,
            frequency=invalid_frequency,
        )

    error = exc_info.value
    assert str(error) == f"Unsupported forecast frequency: '{invalid_frequency}'"
    assert isinstance(error.__cause__, (TypeError, ValueError))
    assert "ValueError" not in str(error)
    assert "KeyError" not in str(error)


def test_future_timestamps_must_match_the_requested_horizon():
    engine, _, _ = make_engine()
    future = pd.DataFrame(
        {
            "date": ["2026-01-01T03:00:00Z"],
        }
    )

    with pytest.raises(ForecastValidationError, match="exactly.*rows"):
        engine.forecast(
            data=make_data(),
            target_cols=["sales"],
            forecast_horizon=2,
            future_data=future,
        )


def test_bolt_rejects_multivariate_and_covariate_requests():
    engine, _, loads = make_engine()

    with pytest.raises(ForecastValidationError, match="univariate"):
        engine.forecast(
            data=make_data(targets=["dx", "dy"]),
            target_cols=["dx", "dy"],
            forecast_horizon=1,
            model="chronos-bolt-base",
        )
    assert loads == []

    data = make_data()
    data["temperature"] = [1.0, 2.0, 3.0]
    with pytest.raises(ForecastValidationError, match="covariates"):
        engine.forecast(
            data=data,
            target_cols=["sales"],
            forecast_horizon=1,
            model="chronos-bolt-base",
        )


def test_bolt_univariate_uses_the_official_univariate_dataframe_path():
    engine, pipeline, loads = make_engine()

    result = engine.forecast(
        data=make_data(),
        target_cols=["sales"],
        forecast_horizon=1,
        model="chronos-bolt-base",
    )

    assert len(result.predictions) == 1
    assert len(loads) == 1
    assert "future_df" not in pipeline.calls[0]
