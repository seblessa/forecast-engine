from unittest.mock import Mock, patch

import pandas as pd
from fastapi.testclient import TestClient

import server


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
