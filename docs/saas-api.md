# SaaS API contract

Status: accepted v1, 2026-08-13.

## Public base URL

The public SaaS API is served at:

```text
https://engine.forecasting-studio.com
```

The public routes intentionally reuse the existing Forecast Engine request and
response contract. The public surface is versioned and authenticated; the
existing local routes remain available without application authentication on
the home network only.

## Authentication

Every public request must include:

```http
Authorization: Bearer <SAAS_API_TOKEN>
```

The token is configured on the Mac Mini through the `SAAS_API_TOKEN`
environment variable. It must not be committed, placed in a URL, or written to
application logs.

Unauthenticated requests return `401`. If the server has not been configured
with a token, the SaaS routes return `503` rather than running without
authentication.

## JSON forecast

```http
POST /v1/saas/forecast
Content-Type: application/json
Authorization: Bearer <SAAS_API_TOKEN>
```

Request example:

```json
{
  "data": [
    {"date": "2025-01-01T00:00:00Z", "target": 84.2},
    {"date": "2025-01-01T01:00:00Z", "target": 86.1},
    {"date": "2025-01-01T02:00:00Z", "target": 85.7}
  ],
  "forecast_horizon": 3,
  "frequency": "h",
  "engine": "chronos2"
}
```

The complete JSON schema is the same as `POST /forecast`, including optional
`datetime_col`, `target_col`, `item_id_col`, `random_state`,
`past_covariates`, and `future_covariates` fields.

Response example:

```json
{
  "predictions": [
    {
      "date": "2025-01-01T03:00:00.000",
      "target_predicted": 86.4,
      "lower_bound": 82.1,
      "upper_bound": 90.8
    }
  ]
}
```

## CSV forecast

```http
POST /v1/saas/forecast/csv
Content-Type: multipart/form-data
Authorization: Bearer <SAAS_API_TOKEN>
```

This has the same fields and file parts as `POST /forecast/csv`: `file`,
`past_covariates_file`, `future_covariates_file`, `datetime_col`, `target_col`,
`item_id_col`, `forecast_horizon`, `frequency`, `engine`, and `random_state`.

## Processing behavior

Forecasts are processed one at a time. A request waits for earlier forecasts to
finish and receives the normal synchronous response. The queue is in memory:
restarting the server drops requests that were still waiting. The deployment
must use one Uvicorn worker; multiple workers would create separate queues and
model caches.

The API does not promise a latency SLA in v1. The SaaS backend must use a
request timeout long enough for model loading and queued forecasts.

## Private routes

These routes are not part of the public SaaS contract and must be reachable
only from the home network or an explicitly configured private network:

```text
/forecast
/forecast/csv
/v2/forecast
/models
/health
/docs
/redoc
/openapi.json
/
```
