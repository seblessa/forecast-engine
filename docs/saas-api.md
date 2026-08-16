# SaaS API contract

Status: accepted v1 compatibility and v2 generic route, 2026-08-16.

## Public base URL

The public SaaS API is served at:

```text
https://engine.forecasting-studio.com
```

The public routes intentionally reuse the Forecast Engine request and response
contracts. The public surface is versioned and authenticated; the existing
local routes remain available without application authentication on the home
network only.

Public routes:

```text
POST /v1/saas/forecast
POST /v1/saas/forecast/csv
POST /v2/saas/forecast
```

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

## Generic v2 JSON forecast

```http
POST /v2/saas/forecast
Content-Type: application/json
Authorization: Bearer <SAAS_API_TOKEN>
```

This is the authenticated public equivalent of private `POST /v2/forecast`.
It uses the same `V2ForecastRequest` fields and stable long-format response;
the public route adds only bearer authentication and ingress routing. New
Forecasting Studio integrations should use this route for one or more related
targets, including native Chronos 2 multivariate requests:

```json
{
  "data": [
    {"date": "2026-01-01T00:00:00Z", "dx": 1.2, "dy": 0.4},
    {"date": "2026-01-01T00:00:01Z", "dx": 1.3, "dy": 0.5},
    {"date": "2026-01-01T00:00:02Z", "dx": 1.4, "dy": 0.6}
  ],
  "target_cols": ["dx", "dy"],
  "forecast_horizon": 1,
  "frequency": "s",
  "model": "chronos2"
}
```

The response contains one record per future timestamp, item, and target. Each
record has `timestamp`, `item_id`, `target_name`, `prediction`, and a
`quantiles` object. `target_cols` can contain one target, two targets, or a
larger generic target list; all use the same core path and related targets are
sent jointly to Chronos 2.

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
