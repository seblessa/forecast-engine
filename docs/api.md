# Forecast Engine API

Status: current unified contract, 2026-08-17.

## Public URL and authentication

Forecasting Studio uses:

```text
https://engine.forecasting-studio.com/forecast
```

Every inference request includes:

```http
Authorization: Bearer <SAAS_API_TOKEN>
```

The token is configured only in the service environment and must never be
committed, put in a URL, sent to a browser, or written to logs. FastAPI checks
the token as well as the Caddy ingress filter. Missing or invalid credentials
return `401`; an unconfigured service returns `503`.

## Forecast request

```http
POST /forecast
Content-Type: application/json
Authorization: Bearer <SAAS_API_TOKEN>
```

```json
{
  "data": [
    {"date": "2026-01-01T00:00:00Z", "sales": 84.2},
    {"date": "2026-01-01T01:00:00Z", "sales": 86.1},
    {"date": "2026-01-01T02:00:00Z", "sales": 85.7}
  ],
  "target_cols": ["sales"],
  "forecast_horizon": 3,
  "datetime_col": "date",
  "item_id_col": null,
  "frequency": "h",
  "model": "chronos2",
  "future_data": null,
  "quantile_levels": [0.1, 0.5, 0.9],
  "batch_size": 256,
  "context_length": null,
  "cross_learning": false
}
```

`data` contains structured records. Each record must include the datetime and
all `target_cols`; records for panel data also include `item_id_col`.
`target_cols` describes related variables within one task. `item_id_col`
identifies separate tasks/items. The same endpoint supports one or many items
and one or many targets.

Additional numeric columns in `data` are historical covariates. `future_data`
contains known future covariates, with exactly `forecast_horizon` rows per
item and timestamps matching the requested frequency. It must not contain
target columns.

The request also accepts `batch_size`, `context_length`, and `cross_learning`
when supported by the selected model. Quantile levels are unique probabilities
strictly between zero and one.

## Forecast response

```json
{
  "predictions": [
    {
      "timestamp": "2026-01-01T03:00:00Z",
      "item_id": null,
      "target_name": "sales",
      "prediction": 86.4,
      "quantiles": {"0.1": 82.1, "0.5": 86.4, "0.9": 90.8}
    }
  ]
}
```

Each prediction identifies its future `timestamp`, `item_id`, and
`target_name`. All numeric values are finite. Timestamps are normalized to
UTC and serialized as ISO 8601 strings with an explicit `Z` suffix. A returned
timestamp can be copied literally into a later `data` record for a direct
round trip; the client must not add `Z` manually or perform timezone
conversion.

Chronos 2 receives `target_cols` together in one native multivariate
inference call. The service does not create separate target-specific routes.

## Models and capabilities

Administrators can query the model registry locally without loading weights:

```http
GET http://127.0.0.1:8000/models
```

The response is the source of truth for configured model names and capabilities:

```json
{
  "models": [
    {
      "id": "chronos2",
      "model_id": "amazon/chronos-2",
      "multivariate": true,
      "covariates": true,
      "cross_learning": true,
      "panel": true,
      "context_length": true
    }
  ]
}
```

Use `chronos2` for related targets and covariates. Use `chronos-bolt-base` for
univariate forecasts without covariates. Forecasting Studio must use the
documented capabilities and must not call `/models` through the public
hostname. An unsupported model capability is a `422` validation response.

## Local operational routes

FastAPI also serves these local-only operations:

```text
GET /health
GET /models
GET /docs
GET /openapi.json
GET /
```

`/health` reports the package version, Chronos version, loaded models, and
pipeline cache count. The public ingress exposes none of these paths.

## Errors

- `200`: forecast completed.
- `401`: bearer token missing or invalid.
- `422`: invalid records, timestamps, columns, horizon, frequency, quantiles, or model options.
- `503`: service token is not configured.
- `500`: unexpected inference failure.
