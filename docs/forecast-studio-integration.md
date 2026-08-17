# Forecasting Studio integration

Status: current handoff for the Forecasting Studio backend, 2026-08-17.

The Forecasting Studio backend calls the single authenticated Forecast Engine
operation. This document contains no token or other secret.

## Endpoint and security

```http
POST https://engine.forecasting-studio.com/forecast
Authorization: Bearer <existing token>
Content-Type: application/json
```

The call is server-to-server. Store the token in the Forecasting Studio
backend secret manager. The browser must never receive it, include it in a
request, or put it in a URL. The Engine keeps the same `SAAS_API_TOKEN`
environment variable and token value.

## Single target

```json
{
  "data": [
    {"date": "2026-01-01T00:00:00Z", "sales": 84.2},
    {"date": "2026-01-01T01:00:00Z", "sales": 86.1},
    {"date": "2026-01-01T02:00:00Z", "sales": 85.7}
  ],
  "target_cols": ["sales"],
  "forecast_horizon": 3,
  "frequency": "h",
  "model": "chronos2"
}
```

## Movement targets

Use the same generic request for Draw-style movement history. `dx` and `dy`
are related variables in one task, so Chronos 2 receives them in one native
multivariate inference call:

```json
{
  "data": [
    {"date": "2026-01-01T00:00:00Z", "dx": 1.2, "dy": 0.4},
    {"date": "2026-01-01T00:00:01Z", "dx": 1.3, "dy": 0.5},
    {"date": "2026-01-01T00:00:02Z", "dx": 1.4, "dy": 0.6}
  ],
  "target_cols": ["dx", "dy"],
  "forecast_horizon": 1,
  "datetime_col": "date",
  "frequency": "s",
  "model": "chronos2"
}
```

The response contains one record per item, target, and future step. Use
`target_name` to distinguish `dx` and `dy`; use `quantiles` for the requested
prediction intervals.

## Known future data

Historical covariates are extra columns in `data`. Known future covariates are
sent as `future_data`:

```json
{
  "data": [
    {"date": "2026-01-01T00:00:00Z", "sales": 10, "temperature": 12},
    {"date": "2026-01-01T01:00:00Z", "sales": 11, "temperature": 13}
  ],
  "target_cols": ["sales"],
  "forecast_horizon": 2,
  "frequency": "h",
  "future_data": [
    {"date": "2026-01-01T02:00:00Z", "temperature": 14},
    {"date": "2026-01-01T03:00:00Z", "temperature": 15}
  ]
}
```

Future records must contain exactly the requested number of rows per item and
timestamps matching the frequency. They must not contain target columns.

## Items, timestamps, and round trips

Set `item_id_col` when records contain multiple independent items. Leave it
null for one item. The same route supports one item or many items, and one
target or many targets.

Responses serialize timestamps as UTC ISO 8601 with an explicit `Z`, for
example `2026-01-01T00:00:03Z`. When appending predictions to the next
context, copy that string literally into the next request. No manual `Z`,
timezone conversion, or knowledge of internal normalization is needed.

## Models and options

Call `GET /models` to inspect capabilities. Use `chronos2` for multivariate
targets, covariates, `future_data`, cross-learning, and context length. Use
`chronos-bolt-base` for univariate forecasts without covariates. Select
`quantile_levels` to request custom intervals; the default is `[0.1, 0.5, 0.9]`.

## Client behavior

Forecasts are synchronous and queued one at a time. Set a timeout long enough
for model loading and queued work. Handle `401` as an authentication/config
problem, `422` as request validation, `503` as a service configuration issue,
and `500` as an engine failure. Do not blindly retry a timed-out POST because
the first request may have completed.

The complete contract and local operations are documented in [the API
reference](api.md). Deployment ownership is documented in [the deployment
runbook](deployment.md).
