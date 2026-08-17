from __future__ import annotations

import importlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Lock
from time import sleep
from unittest.mock import Mock, patch

import pandas as pd
from fastapi.testclient import TestClient

from forecast_engine.core import ForecastResult


api = importlib.import_module("forecast_engine.api.app")
client = TestClient(api.app)


def make_result(
    targets: tuple[str, ...] = ("dx", "dy"),
    *,
    items: tuple[str | None, ...] = (None,),
    horizon: int = 1,
    start: str = "2026-01-01T00:00:02",
) -> ForecastResult:
    rows = []
    for item_index, item_id in enumerate(items):
        timestamps = pd.date_range(start, periods=horizon, freq="s")
        for target_index, target in enumerate(targets):
            for step, timestamp in enumerate(timestamps):
                rows.append(
                    {
                        "timestamp": timestamp,
                        "item_id": item_id,
                        "target_name": target,
                        "prediction": float(item_index + target_index + step + 1),
                        "q_0.1": 0.1,
                        "q_0.5": 0.5,
                        "q_0.9": 0.9,
                    }
                )
    return ForecastResult(
        predictions=pd.DataFrame(rows),
        quantile_levels=(0.1, 0.5, 0.9),
    )


def request(
    *,
    targets: list[str] | None = None,
    horizon: int = 1,
    data: list[dict] | None = None,
    **extra,
) -> dict:
    payload = {
        "data": data
        or [
            {"date": "2026-01-01T00:00:00Z", "dx": 1.0, "dy": 2.0},
            {"date": "2026-01-01T00:00:01Z", "dx": 1.1, "dy": 2.1},
        ],
        "target_cols": targets or ["dx", "dy"],
        "forecast_horizon": horizon,
        "frequency": "s",
    }
    payload.update(extra)
    return payload


def test_forecast_requires_bearer_token(monkeypatch):
    monkeypatch.setenv("SAAS_API_TOKEN", "test-token")

    response = client.post("/forecast", json=request())

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_forecast_rejects_invalid_bearer_token(monkeypatch):
    monkeypatch.setenv("SAAS_API_TOKEN", "test-token")

    response = client.post(
        "/forecast",
        headers={"Authorization": "Bearer wrong-token"},
        json=request(),
    )

    assert response.status_code == 401


def test_forecast_accepts_token_and_returns_the_final_contract(monkeypatch):
    monkeypatch.setenv("SAAS_API_TOKEN", "test-token")
    service = Mock()
    service.forecast.return_value = make_result()

    with patch.object(api, "forecast_service", service):
        response = client.post(
            "/forecast",
            headers={"Authorization": "Bearer test-token"},
            json=request(),
        )

    assert response.status_code == 200
    assert [row["target_name"] for row in response.json()["predictions"]] == [
        "dx",
        "dy",
    ]
    assert all(row["timestamp"].endswith("Z") for row in response.json()["predictions"])
    assert all(row["quantiles"] for row in response.json()["predictions"])
    assert service.forecast.call_args.kwargs["target_cols"] == ["dx", "dy"]


def test_forecast_forwards_future_data_and_runtime_controls(monkeypatch):
    monkeypatch.setenv("SAAS_API_TOKEN", "test-token")
    service = Mock()
    service.forecast.return_value = make_result(("sales",))
    payload = request(
        targets=["sales"],
        data=[
            {
                "date": "2026-01-01T00:00:00Z",
                "sales": 1.0,
                "temperature": 10.0,
            },
            {
                "date": "2026-01-01T00:00:01Z",
                "sales": 2.0,
                "temperature": 11.0,
            },
        ],
        future_data=[
            {"date": "2026-01-01T00:00:02Z", "temperature": 12.0}
        ],
        batch_size=8,
        context_length=64,
        cross_learning=True,
        quantile_levels=[0.2, 0.5, 0.8],
    )

    with patch.object(api, "forecast_service", service):
        response = client.post(
            "/forecast",
            headers={"Authorization": "Bearer test-token"},
            json=payload,
        )

    assert response.status_code == 200
    call = service.forecast.call_args.kwargs
    assert call["target_cols"] == ["sales"]
    assert call["future_data"]["temperature"].tolist() == [12.0]
    assert call["batch_size"] == 8
    assert call["context_length"] == 64
    assert call["cross_learning"] is True
    assert call["quantile_levels"] == [0.2, 0.5, 0.8]


def test_forecast_preserves_items_and_multiple_targets(monkeypatch):
    monkeypatch.setenv("SAAS_API_TOKEN", "test-token")
    service = Mock()
    service.forecast.return_value = make_result(
        items=("A", "B"), targets=("dx", "dy")
    )
    payload = request(
        data=[
            {"date": "2026-01-01T00:00:00Z", "store": "A", "dx": 1, "dy": 2},
            {"date": "2026-01-01T00:00:01Z", "store": "A", "dx": 2, "dy": 3},
            {"date": "2026-01-01T00:00:00Z", "store": "B", "dx": 4, "dy": 5},
            {"date": "2026-01-01T00:00:01Z", "store": "B", "dx": 5, "dy": 6},
        ],
        item_id_col="store",
    )

    with patch.object(api, "forecast_service", service):
        response = client.post(
            "/forecast",
            headers={"Authorization": "Bearer test-token"},
            json=payload,
        )

    assert response.status_code == 200
    assert {row["item_id"] for row in response.json()["predictions"]} == {"A", "B"}
    assert {row["target_name"] for row in response.json()["predictions"]} == {
        "dx",
        "dy",
    }
    assert service.forecast.call_args.kwargs["item_id_col"] == "store"


def test_forecast_round_trip_accepts_returned_timestamp_without_client_changes(
    monkeypatch,
):
    monkeypatch.setenv("SAAS_API_TOKEN", "test-token")
    service = Mock()
    service.forecast.side_effect = [
        make_result(),
        make_result(start="2026-01-01T00:00:03"),
    ]

    with patch.object(api, "forecast_service", service):
        first_response = client.post(
            "/forecast",
            headers={"Authorization": "Bearer test-token"},
            json=request(),
        )
        first_predictions = first_response.json()["predictions"]
        timestamp = first_predictions[0]["timestamp"]
        next_data = request()["data"] + [
            {
                "date": timestamp,
                "dx": first_predictions[0]["prediction"],
                "dy": first_predictions[1]["prediction"],
            }
        ]
        second_response = client.post(
            "/forecast",
            headers={"Authorization": "Bearer test-token"},
            json=request(data=next_data),
        )

    assert first_response.status_code == 200
    assert timestamp == "2026-01-01T00:00:02Z"
    assert second_response.status_code == 200
    received = service.forecast.call_args_list[1].kwargs["data"]
    assert received["date"].iloc[-1] == pd.Timestamp("2026-01-01T00:00:02")


def test_forecast_rejects_invalid_timestamp_and_duplicate_targets(monkeypatch):
    monkeypatch.setenv("SAAS_API_TOKEN", "test-token")

    invalid_timestamp = client.post(
        "/forecast",
        headers={"Authorization": "Bearer test-token"},
        json=request(
            data=[{"date": "not-a-timestamp", "sales": 1}],
            targets=["sales"],
        ),
    )
    duplicate_targets = client.post(
        "/forecast",
        headers={"Authorization": "Bearer test-token"},
        json=request(targets=["dx", "dx"]),
    )

    assert invalid_timestamp.status_code == 422
    assert duplicate_targets.status_code == 422


def test_forecast_sanitizes_invalid_frequency_errors(monkeypatch):
    monkeypatch.setenv("SAAS_API_TOKEN", "test-token")
    invalid_frequency = "not-a-frequency"

    response = client.post(
        "/forecast",
        headers={"Authorization": "Bearer test-token"},
        json=request(targets=["dx"], frequency=invalid_frequency),
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail == f"Unsupported forecast frequency: '{invalid_frequency}'"
    assert "ValueError" not in detail
    assert "KeyError" not in detail


def test_final_request_rejects_removed_fields(monkeypatch):
    monkeypatch.setenv("SAAS_API_TOKEN", "test-token")
    for field in (
        "target_col",
        "engine",
        "random_state",
        "past_covariates",
        "future_covariates",
    ):
        response = client.post(
            "/forecast",
            headers={"Authorization": "Bearer test-token"},
            json=request(**{field: "removed"}),
        )
        assert response.status_code == 422, field


def test_forecasts_are_processed_serially(monkeypatch):
    monkeypatch.setenv("SAAS_API_TOKEN", "test-token")
    active = 0
    maximum_active = 0
    state_lock = Lock()

    def run(*, data, **kwargs):
        nonlocal active, maximum_active
        with state_lock:
            active += 1
            maximum_active = max(maximum_active, active)
        sleep(0.02)
        with state_lock:
            active -= 1
        return make_result(("sales",))

    service = Mock()
    service.forecast.side_effect = run
    headers = {"Authorization": "Bearer test-token"}
    payload = request(
        targets=["sales"],
        data=[
            {"date": "2026-01-01T00:00:00Z", "sales": 1.0},
            {"date": "2026-01-01T00:00:01Z", "sales": 2.0},
        ],
    )
    with patch.object(api, "forecast_service", service):
        with ThreadPoolExecutor(max_workers=2) as executor:
            responses = list(
                executor.map(
                    lambda _: client.post("/forecast", headers=headers, json=payload),
                    range(2),
                )
            )

    assert [response.status_code for response in responses] == [200, 200]
    assert maximum_active == 1


def test_root_redirects_to_docs_and_private_system_routes_are_local_routes():
    root_response = client.get("/", follow_redirects=False)
    health_response = client.get("/health")
    models_response = client.get("/models")

    assert root_response.status_code == 307
    assert root_response.headers["location"] == "/docs"
    assert health_response.status_code == 200
    assert health_response.json()["forecast_engine_version"] == api.PACKAGE_VERSION
    assert client.get("/openapi.json").json()["info"]["version"] == api.PACKAGE_VERSION
    assert "chronos_forecasting_version" in health_response.json()
    assert "cached_pipelines" in health_response.json()
    assert models_response.status_code == 200
    assert {model["id"] for model in models_response.json()["models"]} == {
        "chronos2",
        "chronos-bolt-base",
    }


def test_openapi_describes_one_forecast_route_and_bearer_auth():
    schema = client.get("/openapi.json").json()

    assert set(schema["paths"]) == {"/forecast", "/health", "/models"}
    forecast_schema = schema["paths"]["/forecast"]["post"]
    assert forecast_schema["security"]
    assert "HTTPBearer" in schema["components"]["securitySchemes"]
    request_schema = schema["components"]["schemas"]["ForecastRequest"]
    assert set(request_schema["properties"]) == {
        "data",
        "target_cols",
        "forecast_horizon",
        "datetime_col",
        "item_id_col",
        "frequency",
        "model",
        "future_data",
        "quantile_levels",
        "batch_size",
        "context_length",
        "cross_learning",
    }


def test_removed_routes_are_not_registered():
    for path in (
        "/v1/saas/forecast",
        "/v1/saas/forecast/csv",
        "/v2/saas/forecast",
        "/v2/forecast",
        "/forecast/csv",
    ):
        response = client.post(path, json=request())
        assert response.status_code == 404, path


def test_caddy_publishes_only_the_final_forecast_path():
    caddyfile = (Path(__file__).parents[1] / "infra" / "Caddyfile").read_text()
    assert "@forecast {" in caddyfile
    assert "method POST" in caddyfile
    assert "path /forecast" in caddyfile
    assert "reverse_proxy 127.0.0.1:8000" in caddyfile
    assert "respond 404" in caddyfile
