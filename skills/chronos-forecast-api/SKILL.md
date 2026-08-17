---
name: chronos-forecast-api
description: Generate time-series forecasts through the Forecast Engine REST API backed by official Amazon Chronos pipelines. Use for univariate, multivariate, panel, covariate-informed, or prediction-interval forecasts over HTTP.
---

# Forecast Engine API

Use the Forecast Engine for structured time-series forecasts. The service must
be running before making a request; do not silently substitute another method.

## Endpoint and authentication

The public endpoint is:

```text
POST https://engine.forecasting-studio.com/forecast
```

Include the bearer token from the backend secret store:

```http
Authorization: Bearer <SAAS_API_TOKEN>
User-Agent: ForecastStudio-SaaS/1.0
```

This is a server-to-server call. Never put the token in browser code, a URL,
source control, or logs. For local development use the same path on
`http://localhost:8000`.

## Request contract

The JSON body contains:

- `data`: historical JSON records;
- `target_cols`: one or more related target columns;
- `forecast_horizon`: positive number of future steps;
- `datetime_col`: datetime field, default `date`;
- `item_id_col`: optional item/task identifier;
- `frequency`: pandas frequency such as `s`, `h`, or `D`;
- `model`: configured model name, normally `chronos2`;
- `future_data`: known future records for covariates;
- `quantile_levels`, `batch_size`, `context_length`, and `cross_learning`.

Use extra columns in `data` for historical covariates. Put known future
covariates in `future_data`; include exactly the requested future timestamps
and do not include target columns there.

`target_cols` describes related variables in one task. `item_id_col` separates
independent tasks/items. The same endpoint supports one item or many items and
one target or many targets.

## Movement example

```bash
curl --fail-with-body \
  -X POST 'https://engine.forecasting-studio.com/forecast' \
  -H 'Authorization: Bearer <SAAS_API_TOKEN>' \
  -H 'Content-Type: application/json' \
  -H 'User-Agent: ForecastStudio-SaaS/1.0' \
  -d '{
    "data": [
      {"date":"2026-01-01T00:00:00Z","dx":1.2,"dy":0.4},
      {"date":"2026-01-01T00:00:01Z","dx":1.3,"dy":0.5},
      {"date":"2026-01-01T00:00:02Z","dx":1.4,"dy":0.6}
    ],
    "target_cols":["dx","dy"],
    "forecast_horizon":1,
    "datetime_col":"date",
    "frequency":"s",
  "model":"chronos2"
  }'
```

Chronos 2 receives `dx` and `dy` together in one native multivariate call.
There is no product-specific route.

## Response and timestamps

Each response record contains:

```json
{
  "timestamp": "2026-01-01T00:00:03Z",
  "item_id": null,
  "target_name": "dx",
  "prediction": 1.25,
  "quantiles": {"0.1": 1.0, "0.5": 1.25, "0.9": 1.5}
}
```

Timestamps are explicit UTC ISO 8601 strings with a `Z` suffix. Copy a
returned timestamp literally into a later input record for a sequential
round trip. Do not append `Z` manually or convert the timezone in the client.

## Local operations, models, and errors

For local administration only, the service also provides `GET /health`,
`GET /models`, `GET /docs`, and `GET /openapi.json` on
`http://localhost:8000`. These operational endpoints are not published through
the public hostname, and Forecasting Studio must not call them publicly.

Use the local `/models` source of truth to inspect capabilities. `chronos2`
supports multivariate targets, covariates, panel items, future data,
cross-learning, and context length. `chronos-bolt-base` supports univariate
forecasts without covariates. Select `quantile_levels` for custom intervals.

Handle `401` for missing or invalid authentication, `422` for invalid data or
unsupported model options, `503` for missing service configuration, and `500`
for unexpected inference failures. Forecasts are synchronous and may wait for
another request while model inference is running, so use an appropriate
timeout.
