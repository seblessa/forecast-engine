from unittest.mock import patch

import pandas as pd
from fastapi.testclient import TestClient

import server


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
        response = TestClient(server.app).post("/forecast", json=request)

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
        response = TestClient(server.app).post("/forecast", json=request)

    assert response.status_code == 200
    assert [row["store"] for row in response.json()["predictions"]] == ["A", "B"]
