---
name: chronos-forecast-api
description: Generate time-series forecasts through the Forecast Engine REST API backed by official Amazon chronos-forecasting pipelines. Use for univariate, multivariate, panel, covariate-informed, or prediction-interval forecasts over HTTP.
---

# Use the Chronos Forecast API

Treat the service as a forecasting tool. Do not install ML packages or
recreate the model in a consuming project.

## Locate and check the service

Use `CHRONOS_API_URL` when set; otherwise use `http://localhost:8000`. Call
`GET /health` before forecasting. If it is unavailable, report that the
Forecast Engine must be started; do not silently substitute another method.

`GET /models` lists the configured aliases and capabilities without loading
model weights.

## Prefer the v2 endpoint

Use `POST /v2/forecast` for new work. Its request contains:

- `data`: non-empty historical records;
- `target_cols`: one or more related target columns;
- `forecast_horizon`: positive number of future steps;
- `datetime_col`, `item_id_col`, and `frequency` matching the data;
- `model`: normally `chronos2`;
- `future_data`: optional known-future covariate records;
- `quantile_levels`, `batch_size`, `context_length`, and `cross_learning`.

`target_cols` describes related variables in one task. `item_id_col` describes
separate tasks/items. Use both for panel data with multiple related targets.
Chronos 2 forecasts multiple targets jointly; do not split them into
independent requests.

Example:

```bash
curl -sS "${CHRONOS_API_URL:-http://localhost:8000}/v2/forecast" \
  -H 'Content-Type: application/json' \
  -d '{
    "data": [
      {"date": "2026-01-01T00:00:00Z", "dx": 1.2, "dy": 0.4},
      {"date": "2026-01-01T00:00:01Z", "dx": 1.3, "dy": 0.5},
      {"date": "2026-01-01T00:00:02Z", "dx": 1.4, "dy": 0.6}
    ],
    "target_cols": ["dx", "dy"],
    "forecast_horizon": 1,
    "frequency": "s",
    "model": "chronos2",
    "quantile_levels": [0.1, 0.5, 0.9]
  }'
```

The response uses stable long format:

```json
{
  "predictions": [
    {
      "timestamp": "2026-01-01T00:00:03",
      "item_id": null,
      "target_name": "dx",
      "prediction": 0.9,
      "quantiles": {"0.1": 0.6, "0.5": 0.9, "0.9": 1.2}
    }
  ]
}
```

Historical covariates are additional columns in `data`. Known future
covariates go in `future_data`; do not invent future values and never include
future target values. `cross_learning` is optional Chronos 2 information
sharing across separate tasks/items and is different from multivariate target
columns.

## Models and unsupported options

The configured aliases are:

- `chronos2` → `amazon/chronos-2`: univariate, multivariate, panel,
  historical/future covariates, cross-learning, and context length.
- `chronos-bolt-base` → `amazon/chronos-bolt-base`: univariate panel forecasts
  without covariates, future data, cross-learning, or client context length.

Requests for unsupported capabilities return HTTP 422. Do not silently ignore
fields. Quantile levels must be unique and strictly between 0 and 1; the
default is `[0.1, 0.5, 0.9]`.

## Legacy input modes

Use `POST /forecast` when a caller requires the existing singular-target
contract. It accepts:

- `data`, `forecast_horizon`, `datetime_col`, `target_col`, `frequency`;
- `item_id_col` for panel data;
- `engine: "chronos2"` or the compatibility `engine: "chronos"`;
- `past_covariates` and `future_covariates` with Chronos 2.

Use `POST /forecast/csv` for local CSV files. Upload `file` and optionally
`past_covariates_file` and `future_covariates_file`. All files must share the
timestamp column and, for panel data, the item ID column.

Legacy responses retain `target_predicted`, `lower_bound`, and `upper_bound`.
Use v2 when dynamic target names and multiple related targets are needed.

Preserve returned timestamps and units. Prediction intervals are uncertainty
bands, not guarantees. Surface HTTP validation errors with the invalid field or
column; retry only after correcting the request.
