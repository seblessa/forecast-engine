from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Lock
from time import sleep
from unittest.mock import Mock, patch

import pandas as pd
from fastapi.testclient import TestClient

import server
from forecast_engine.core import ForecastResult


client = TestClient(server.app)


class FakeForecaster:
    def predict(self, data, **kwargs):
        assert list(data.columns) == ["date", "target"]
        return pd.DataFrame(
            [
                {
                    "date": pd.Timestamp("2025-01-01T03:00:00"),
                    "target_predicted": 86.4,
                    "lower_bound": 82.1,
                    "upper_bound": 90.8,
                }
            ]
        )


def test_forecast_returns_json_records():
    request = {
        "data": [
            {"date": "2025-01-01T00:00:00", "target": 84.2},
            {"date": "2025-01-01T01:00:00", "target": 86.1},
        ],
        "forecast_horizon": 1,
    }

    with patch.object(server, "get_forecaster", return_value=FakeForecaster()):
        response = client.post("/forecast", json=request)

    assert response.status_code == 200
    assert response.json() == {
        "predictions": [
            {
                "date": "2025-01-01T03:00:00.000",
                "target_predicted": 86.4,
                "lower_bound": 82.1,
                "upper_bound": 90.8,
            }
        ]
    }


def test_saas_forecast_rejects_missing_bearer_token(monkeypatch):
    monkeypatch.setenv("SAAS_API_TOKEN", "test-token")
    response = client.post(
        "/v1/saas/forecast",
        json={
            "data": [{"date": "2025-01-01T00:00:00", "target": 84.2}],
            "forecast_horizon": 1,
        },
    )

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_saas_forecast_reuses_json_contract(monkeypatch):
    monkeypatch.setenv("SAAS_API_TOKEN", "test-token")
    request = {
        "data": [
            {"date": "2025-01-01T00:00:00", "target": 84.2},
            {"date": "2025-01-01T01:00:00", "target": 86.1},
        ],
        "forecast_horizon": 1,
    }

    with patch.object(server, "get_forecaster", return_value=FakeForecaster()):
        response = client.post(
            "/v1/saas/forecast",
            headers={"Authorization": "Bearer test-token"},
            json=request,
        )

    assert response.status_code == 200
    assert response.json()["predictions"][0]["target_predicted"] == 86.4


def test_saas_csv_rejects_missing_bearer_token(monkeypatch):
    monkeypatch.setenv("SAAS_API_TOKEN", "test-token")
    response = client.post(
        "/v1/saas/forecast/csv",
        files={"file": ("history.csv", b"date,target\n2025-01-01,84.2\n", "text/csv")},
    )

    assert response.status_code == 401


def test_saas_routes_are_documented_with_bearer_auth():
    schema = client.get("/openapi.json").json()

    assert schema["paths"]["/v1/saas/forecast"]["post"]["security"]
    assert schema["paths"]["/v1/saas/forecast/csv"]["post"]["security"]
    assert schema["paths"]["/v2/saas/forecast"]["post"]["security"]
    assert "HTTPBearer" in schema["components"]["securitySchemes"]


def test_forecasts_are_processed_serially():
    active = 0
    maximum_active = 0
    state_lock = Lock()

    class SerialForecaster:
        def predict(self, data, **kwargs):
            nonlocal active, maximum_active
            with state_lock:
                active += 1
                maximum_active = max(maximum_active, active)
            sleep(0.02)
            with state_lock:
                active -= 1
            return pd.DataFrame(
                [{"date": pd.Timestamp("2025-01-01"), "target_predicted": 1.0}]
            )

    request = server.ForecastRequest(
        data=[{"date": "2025-01-01", "target": 1.0}], forecast_horizon=1
    )
    with patch.object(server, "get_forecaster", return_value=SerialForecaster()):
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(server._run_forecast, [request, request]))

    assert len(results) == 2
    assert maximum_active == 1


def test_forecast_preserves_panel_item_ids():
    request = {
        "data": [
            {"date": "2025-01-01", "target": 1, "store": "A"},
            {"date": "2025-01-01", "target": 2, "store": "B"},
        ],
        "forecast_horizon": 1,
        "item_id_col": "store",
    }
    predictions = pd.DataFrame(
        [
            {"date": "2025-01-02", "target_predicted": 1.1},
            {"date": "2025-01-02", "target_predicted": 2.1},
        ]
    )
    fake = FakeForecaster()
    fake.predict = lambda *args, **kwargs: predictions

    with patch.object(server, "get_forecaster", return_value=fake):
        response = client.post("/forecast", json=request)

    assert response.status_code == 200
    assert [row["store"] for row in response.json()["predictions"]] == ["A", "B"]


def test_root_redirects_to_docs():
    response = client.get("/", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "/docs"


def test_csv_upload_builds_forecast_request():
    csv = b"date,target\n2025-01-01T00:00:00,84.2\n2025-01-01T01:00:00,86.1\n"

    with patch.object(server, "get_forecaster", return_value=FakeForecaster()):
        response = client.post(
            "/forecast/csv",
            files={"file": ("history.csv", csv, "text/csv")},
            data={
                "datetime_col": "date",
                "target_col": "target",
                "forecast_horizon": "1",
                "frequency": "h",
                "engine": "chronos2",
            },
        )

    assert response.status_code == 200
    assert response.json()["predictions"][0]["target_predicted"] == 86.4


def test_csv_upload_normalizes_timezone_aware_timestamps_to_naive_utc():
    csv = (
        b"date,target\n"
        b"2025-03-30T00:00:00+00:00,84.2\n"
        b"2025-03-30T02:00:00+01:00,86.1\n"
    )
    forecaster = Mock()
    forecaster.predict.return_value = pd.DataFrame(
        [{"date": pd.Timestamp("2025-03-30T02:00:00"), "target_predicted": 87.0}]
    )

    with patch.object(server, "get_forecaster", return_value=forecaster):
        response = client.post(
            "/forecast/csv",
            files={"file": ("history.csv", csv, "text/csv")},
            data={
                "datetime_col": "date",
                "target_col": "target",
                "forecast_horizon": "1",
                "frequency": "h",
            },
        )

    assert response.status_code == 200
    received = forecaster.predict.call_args.args[0]
    assert received["date"].tolist() == [
        pd.Timestamp("2025-03-30T00:00:00"),
        pd.Timestamp("2025-03-30T01:00:00"),
    ]
    assert received["date"].dt.tz is None


def test_json_forecast_normalizes_panel_and_covariate_timestamps():
    forecaster = Mock()
    forecaster.predict.return_value = pd.DataFrame(
        [{"date": pd.Timestamp("2025-03-30T02:00:00"), "target_predicted": 87.0}]
    )
    request = {
        "data": [
            {"date": "2025-03-30T00:00:00+00:00", "target": 84.2, "store": "A"},
            {"date": "2025-03-30T02:00:00+01:00", "target": 86.1, "store": "A"},
        ],
        "past_covariates": [
            {"date": "2025-03-30T00:00:00+00:00", "temperature": 12, "store": "A"}
        ],
        "future_covariates": [
            {"date": "2025-03-30T02:00:00+01:00", "temperature": 13, "store": "A"}
        ],
        "forecast_horizon": 1,
        "item_id_col": "store",
    }

    with patch.object(server, "get_forecaster", return_value=forecaster):
        response = client.post("/forecast", json=request)

    assert response.status_code == 200
    data = forecaster.predict.call_args.args[0]
    past = forecaster.predict.call_args.kwargs["past_covariates_df"]
    future = forecaster.predict.call_args.kwargs["future_covariates_df"]
    assert data["date"].tolist() == [
        pd.Timestamp("2025-03-30T00:00:00"),
        pd.Timestamp("2025-03-30T01:00:00"),
    ]
    assert past["date"].dt.tz is None
    assert future["date"].dt.tz is None
    assert data["store"].tolist() == ["A", "A"]


def test_csv_upload_passes_covariates_and_panel_configuration():
    historical = b"date,target,store\n2025-01-01,84.2,A\n2025-01-02,86.1,A\n"
    past = b"date,temperature,store\n2025-01-01,12,A\n2025-01-02,13,A\n"
    future = b"date,temperature,store\n2025-01-03,14,A\n"
    result = pd.DataFrame(
        [{"date": "2025-01-03", "target_predicted": 87, "store": "A"}]
    )
    forecaster = Mock()
    forecaster.predict.return_value = result

    with patch.object(server, "get_forecaster", return_value=forecaster):
        response = client.post(
            "/forecast/csv",
            files={
                "file": ("history.csv", historical, "text/csv"),
                "past_covariates_file": ("past.csv", past, "text/csv"),
                "future_covariates_file": ("future.csv", future, "text/csv"),
            },
            data={
                "datetime_col": "date",
                "target_col": "target",
                "item_id_col": "store",
                "forecast_horizon": "1",
                "frequency": "D",
                "engine": "chronos2",
                "random_state": "7",
            },
        )

    assert response.status_code == 200
    call = forecaster.predict.call_args
    assert list(call.kwargs["past_covariates_df"].columns) == [
        "date",
        "temperature",
        "store",
    ]
    assert list(call.kwargs["future_covariates_df"].columns) == [
        "date",
        "temperature",
        "store",
    ]


def make_v2_result(targets=("dx", "dy")):
    return ForecastResult(
        predictions=pd.DataFrame(
            [
                {
                    "timestamp": pd.Timestamp("2026-01-01T00:00:01"),
                    "item_id": None,
                    "target_name": target,
                    "prediction": float(index + 1),
                    "q_0.1": 0.1,
                    "q_0.5": 0.5,
                    "q_0.9": 0.9,
                }
                for index, target in enumerate(targets)
            ]
        ),
        quantile_levels=(0.1, 0.5, 0.9),
    )


def test_v2_forecast_uses_stable_long_format_and_target_list():
    engine = Mock()
    engine.forecast.return_value = make_v2_result()
    with patch.object(server, "forecast_engine", engine):
        response = client.post(
            "/v2/forecast",
            json={
                "data": [
                    {"date": "2026-01-01T00:00:00Z", "dx": 1.0, "dy": 2.0},
                    {"date": "2026-01-01T00:00:01Z", "dx": 1.1, "dy": 2.1},
                ],
                "target_cols": ["dx", "dy"],
                "forecast_horizon": 1,
                "frequency": "s",
            },
        )

    assert response.status_code == 200
    assert response.json() == {
        "predictions": [
            {
                "timestamp": "2026-01-01T00:00:01Z",
                "item_id": None,
                "target_name": "dx",
                "prediction": 1.0,
                "quantiles": {"0.1": 0.1, "0.5": 0.5, "0.9": 0.9},
            },
            {
                "timestamp": "2026-01-01T00:00:01Z",
                "item_id": None,
                "target_name": "dy",
                "prediction": 2.0,
                "quantiles": {"0.1": 0.1, "0.5": 0.5, "0.9": 0.9},
            },
        ]
    }
    call = engine.forecast.call_args.kwargs
    assert call["target_cols"] == ["dx", "dy"]
    assert call["frequency"] == "s"


def test_saas_v2_rejects_missing_bearer_token(monkeypatch):
    monkeypatch.setenv("SAAS_API_TOKEN", "test-token")
    response = client.post(
        "/v2/saas/forecast",
        json={
            "data": [{"date": "2026-01-01T00:00:00Z", "dx": 1.0, "dy": 2.0}],
            "target_cols": ["dx", "dy"],
            "forecast_horizon": 1,
        },
    )

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_saas_v2_rejects_invalid_bearer_token(monkeypatch):
    monkeypatch.setenv("SAAS_API_TOKEN", "test-token")
    response = client.post(
        "/v2/saas/forecast",
        headers={"Authorization": "Bearer wrong-token"},
        json={
            "data": [{"date": "2026-01-01T00:00:00Z", "dx": 1.0, "dy": 2.0}],
            "target_cols": ["dx", "dy"],
            "forecast_horizon": 1,
        },
    )

    assert response.status_code == 401


def test_saas_v2_accepts_token_and_reuses_v2_core_contract(monkeypatch):
    monkeypatch.setenv("SAAS_API_TOKEN", "test-token")
    engine = Mock()
    engine.forecast.return_value = make_v2_result()
    request = {
        "data": [
            {"date": "2026-01-01T00:00:00Z", "dx": 1.0, "dy": 2.0},
            {"date": "2026-01-01T00:00:01Z", "dx": 1.1, "dy": 2.1},
        ],
        "target_cols": ["dx", "dy"],
        "forecast_horizon": 1,
        "frequency": "s",
    }

    with patch.object(server, "forecast_engine", engine):
        response = client.post(
            "/v2/saas/forecast",
            headers={"Authorization": "Bearer test-token"},
            json=request,
        )

    assert response.status_code == 200
    assert [row["target_name"] for row in response.json()["predictions"]] == [
        "dx",
        "dy",
    ]
    assert all(row["quantiles"] for row in response.json()["predictions"])
    assert all(row["timestamp"].endswith("Z") for row in response.json()["predictions"])
    assert engine.forecast.call_args.kwargs["target_cols"] == ["dx", "dy"]


def test_saas_v2_and_private_v2_share_the_same_handler():
    public_route = next(
        route
        for route in server.v2_saas_router.routes
        if route.path == "/v2/saas/forecast"
    )

    private_route = next(
        route for route in server.app.routes if getattr(route, "path", None) == "/v2/forecast"
    )
    assert private_route.endpoint is server.forecast_v2
    assert public_route.endpoint is server.forecast_v2


def test_public_ingress_allowlist_publishes_only_authenticated_saas_paths():
    caddyfile = (Path(__file__).parents[1] / "infra" / "Caddyfile").read_text()
    matcher = next(
        line.strip() for line in caddyfile.splitlines() if "@saas path" in line
    )
    paths = set(matcher.split()[2:])

    assert paths == {
        "/v1/saas/forecast",
        "/v1/saas/forecast/csv",
        "/v2/saas/forecast",
    }
    assert "respond 404" in caddyfile


def test_v2_forwards_covariates_and_runtime_controls():
    engine = Mock()
    engine.forecast.return_value = make_v2_result(("sales",))
    with patch.object(server, "forecast_engine", engine):
        response = client.post(
            "/v2/forecast",
            json={
                "data": [
                    {
                        "date": "2026-01-01T00:00:00Z",
                        "sales": 1.0,
                        "temperature": 10.0,
                    },
                    {
                        "date": "2026-01-01T01:00:00Z",
                        "sales": 2.0,
                        "temperature": 11.0,
                    },
                ],
                "future_data": [
                    {"date": "2026-01-01T02:00:00Z", "temperature": 12.0}
                ],
                "target_cols": ["sales"],
                "forecast_horizon": 1,
                "batch_size": 8,
                "context_length": 64,
                "cross_learning": True,
                "quantile_levels": [0.2, 0.5, 0.8],
            },
        )

    assert response.status_code == 200
    call = engine.forecast.call_args.kwargs
    assert call["future_data"]["temperature"].tolist() == [12.0]
    assert call["batch_size"] == 8
    assert call["context_length"] == 64
    assert call["cross_learning"] is True
    assert call["quantile_levels"] == [0.2, 0.5, 0.8]


def test_v2_rejects_duplicate_targets():
    response = client.post(
        "/v2/forecast",
        json={
            "data": [{"date": "2026-01-01T00:00:00Z", "sales": 1.0}],
            "target_cols": ["sales", "sales"],
            "forecast_horizon": 1,
        },
    )

    assert response.status_code == 422


def test_models_and_openapi_expose_the_new_contract_without_loading_models():
    health = client.get("/health")
    models = client.get("/models")
    schema = client.get("/openapi.json").json()

    assert health.status_code == 200
    assert "chronos_forecasting_version" in health.json()
    assert models.status_code == 200
    assert {model["id"] for model in models.json()["models"]} == {
        "chronos2",
        "chronos-bolt-base",
    }
    assert "/v2/forecast" in schema["paths"]
    assert "/models" in schema["paths"]
