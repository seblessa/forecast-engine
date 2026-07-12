---
name: chronos-forecast-api
description: Generate time-series forecasts by calling a running Forecast Engine REST API backed by chronos_forecaster. Use when an agent must forecast timestamped values, obtain prediction intervals, use Chronos-2 covariates, or work with multiple time series through HTTP instead of implementing or running a forecasting model directly.
---

# Use the Chronos Forecast API

Treat the service as a forecasting tool. Do not install ML packages or recreate
the model in the consuming project.

## Locate and check the service

Use `CHRONOS_API_URL` when it is set; otherwise use `http://localhost:8000`.
Call `GET /health` before forecasting. If it is unavailable, report that the
Forecast Engine server must be started; do not silently substitute another
forecasting method.

## Choose the input mode

- Use `POST /forecast` when observations are already structured in memory or the
  agent must build the request manually as JSON.
- Use `POST /forecast/csv` when the user provides a local CSV. Upload the file
  directly instead of rewriting all rows into JSON.

## Send JSON

Call `POST /forecast` with JSON containing:

- `data`: non-empty timestamped observations.
- `forecast_horizon`: positive number of future steps.
- `datetime_col`, `target_col`, `frequency`: match the input schema and cadence.
- `engine`: use `chronos2` by default; use `chronos` only when explicitly asked.
- `item_id_col`: include for panel data with multiple series.
- `past_covariates` and `future_covariates`: include only with `chronos2`. Never
  invent future covariate values; they must be known at forecast time.

Example:

```bash
curl -sS "${CHRONOS_API_URL:-http://localhost:8000}/forecast" \
  -H 'Content-Type: application/json' \
  -d '{
    "data": [
      {"date": "2025-01-01T00:00:00", "target": 84.2},
      {"date": "2025-01-01T01:00:00", "target": 86.1}
    ],
    "forecast_horizon": 3,
    "datetime_col": "date",
    "target_col": "target",
    "frequency": "h",
    "engine": "chronos2"
  }'
```

## Send CSV files

Call `POST /forecast/csv` as multipart form data with:

- `file`: required historical target CSV.
- `datetime_col`, `target_col`: matching column names in `file`.
- `forecast_horizon`, `frequency`, `engine`, `random_state`: forecast settings.
- `item_id_col`: series identifier column for panel data; omit for one series.
- `past_covariates_file`: optional historical covariates CSV for Chronos-2.
- `future_covariates_file`: optional known future covariates CSV for Chronos-2.

All CSVs must share `datetime_col` and, when set, `item_id_col`. Treat every
other column in the covariate files as a variable. Never invent future covariate
values or send covariates with the `chronos` engine.

```bash
curl -sS "${CHRONOS_API_URL:-http://localhost:8000}/forecast/csv" \
  -F 'file=@history.csv' \
  -F 'past_covariates_file=@past_covariates.csv' \
  -F 'future_covariates_file=@future_covariates.csv' \
  -F 'datetime_col=date' \
  -F 'target_col=target' \
  -F 'forecast_horizon=24' \
  -F 'frequency=h' \
  -F 'engine=chronos2'
```

## Use the result

Read `predictions`. Each record contains the forecast timestamp, the
`<target_col>_predicted` point estimate, `lower_bound`, and `upper_bound` for the
80% prediction interval.

Preserve the returned timestamps and units. State the engine, horizon, cadence,
and prediction interval when presenting results. Do not describe the interval as
a guarantee. Surface HTTP validation errors to the user with the invalid field or
column; retry only after correcting the request.
