# Forecast Engine

Forecast Engine is a reusable Python forecasting core and a thin FastAPI REST
service built directly on Amazon's official
[`chronos-forecasting`](https://github.com/amazon-science/chronos-forecasting)
package. The selected stable release is `2.3.1`.

The application owns request validation, model aliases, pipeline reuse,
compatibility formatting, and the Python/HTTP contracts. The official Chronos
package owns model behavior and inference internals. There is no runtime or
packaging dependency on the former `chronos_forecaster` wrapper.

## Architecture

```text
Consumer
  ↓
FastAPI transport (server.py)
  ↓
forecast_engine.ForecastEngine
  ↓
ModelRegistry + PipelineManager
  ↓
official chronos-forecasting pipelines
  ↓
Chronos 2 / Chronos-Bolt
```

`PipelineManager` loads one pipeline per model identity, device, dtype, and
optional revision. Forecast horizon, target columns, item IDs, frequency,
quantiles, batch size, and context length are request parameters and do not
create additional model copies.

## Requirements and setup

- Python 3.10–3.13
- [`uv`](https://docs.astral.sh/uv/)
- Enough disk and memory for the selected Hugging Face model

Install the locked environment:

```bash
uv sync --locked
```

Start the compatible server entrypoint:

```bash
uv run python server.py
```

The server listens on `0.0.0.0:8000` by default. Override it with
`HOST` and `PORT`. Device, dtype, and model revision are server settings:
`FORECAST_DEVICE`, `FORECAST_DTYPE`, and `FORECAST_MODEL_REVISION`.
They are not client-controlled request fields.

The first request for a model downloads its weights from Hugging Face. Health
and model-capability requests never trigger a download.

## Endpoints

Private/local routes:

- `GET /health` — readiness and cache information.
- `GET /models` — configured aliases and capabilities.
- `POST /forecast` — existing singular-target JSON contract.
- `POST /forecast/csv` — existing CSV contract, including legacy covariate files.
- `POST /v2/forecast` — canonical generic target-list API.
- `GET /docs` and `GET /openapi.json` — interactive and machine-readable API docs.

The existing production ingress publishes only the authenticated SaaS routes
`POST /v1/saas/forecast`, `POST /v1/saas/forecast/csv`, and
`POST /v2/saas/forecast` at `https://engine.forecasting-studio.com`. The
public v2 route uses the same request and response contract as private
`POST /v2/forecast`, with the existing bearer token added by the SaaS backend.
The ingress does not publish the private documentation, health, model, legacy
local, or private v2 routes.
See the [SaaS API contract](docs/saas-api.md) and
[deployment runbook](docs/saas-deployment.md).

## Canonical v2 API

Use one request shape for one or many related targets:

```bash
curl -X POST http://localhost:8000/v2/forecast \
  -H 'Content-Type: application/json' \
  -d '{
    "data": [
      {"date": "2026-01-01T00:00:00Z", "dx": 1.2, "dy": 0.4},
      {"date": "2026-01-01T00:00:01Z", "dx": 1.3, "dy": 0.5},
      {"date": "2026-01-01T00:00:02Z", "dx": 1.4, "dy": 0.6}
    ],
    "target_cols": ["dx", "dy"],
    "forecast_horizon": 1,
    "datetime_col": "date",
    "frequency": "s",
    "model": "chronos2",
    "quantile_levels": [0.1, 0.5, 0.9]
  }'
```

`target_cols` identifies related variables in one forecasting task. The
implementation passes all target columns jointly to Chronos 2's native
multivariate path; it does not loop over targets independently.

`item_id_col` identifies separate tasks/items in panel data. Both dimensions
can coexist: one item with many targets, many items with one target, or many
items with many targets. `batch_size` controls the official pipeline batching;
it does not change the target/item semantics.

The response is stable long format and does not create dynamic fields such as
`dx_predicted` or `dy_predicted`:

```json
{
  "predictions": [
    {
      "timestamp": "2026-01-01T00:00:03Z",
      "item_id": null,
      "target_name": "dx",
      "prediction": 0.9,
      "quantiles": {"0.1": 0.6, "0.5": 0.9, "0.9": 1.2}
    }
  ]
}
```

V2 response timestamps are explicit UTC ISO 8601 values with a `Z` suffix.
Pass a returned `timestamp` directly into the next request when appending
predictions to the context; the client must not append `Z` manually or convert
the timezone. This supports sequential consumers such as Forecasting Studio
Draw.

Chronos 2 also accepts historical covariates as additional columns in
`data`. Known future covariates belong in `future_data` and must have exactly
one row per item and horizon step. Future target values are rejected. For
example:

```json
{
  "data": [
    {"date": "2026-01-01T00:00:00Z", "sales": 10, "pressure": 100},
    {"date": "2026-01-01T01:00:00Z", "sales": 11, "pressure": 101},
    {"date": "2026-01-01T02:00:00Z", "sales": 12, "pressure": 102}
  ],
  "future_data": [
    {"date": "2026-01-01T03:00:00Z", "pressure": 103}
  ],
  "target_cols": ["sales"],
  "forecast_horizon": 1,
  "frequency": "h"
}
```

`cross_learning` is disabled by default. When enabled for Chronos 2 it is
passed to the official cross-learning mode across separate tasks/items; it is
distinct from putting multiple target columns in one item. `context_length`
and `batch_size` are also passed to Chronos 2. Quantile levels must be unique
numbers strictly between 0 and 1; the default is `0.1`, `0.5`, and `0.9`.

Configured models are:

| Alias | Model ID | Multivariate | Covariates | Cross learning |
| --- | --- | ---: | ---: | ---: |
| `chronos2` | `amazon/chronos-2` | yes | yes | yes |
| `chronos-bolt-base` | `amazon/chronos-bolt-base` | no | no | no |

The legacy `engine: "chronos"` value maps to `chronos-bolt-base`.
Chronos-Bolt requests for multiple targets, covariates, future data, or
cross-learning fail with HTTP 422 instead of being silently ignored.

## Legacy compatibility

Existing `/forecast` requests keep their `data`, `target_col`, `item_id_col`,
`forecast_horizon`, `frequency`, `engine`, `past_covariates`, and
`future_covariates` fields and retain the historical response keys:

```json
{
  "predictions": [
    {
      "date": "2026-01-01T03:00:00.000",
      "target_predicted": 12.4,
      "lower_bound": 10.1,
      "upper_bound": 14.8
    }
  ]
}
```

`POST /forecast/csv` retains the `file`,
`past_covariates_file`, and `future_covariates_file` multipart fields. These
routes are adapters over the same core inference path; they do not maintain a
second model implementation. Timezone-aware timestamps are normalized to UTC
naive timestamps as in the existing service.

## Python API

The core does not depend on FastAPI or Pydantic request objects:

```python
import pandas as pd

from forecast_engine import ForecastEngine

engine = ForecastEngine()
result = engine.forecast(
    data=df,
    target_cols=["dx", "dy"],
    forecast_horizon=1,
    datetime_col="date",
    frequency="s",
)

records = result.to_records()
```

`result.predictions` is a pandas long-format DataFrame with `timestamp`,
`item_id`, `target_name`, `prediction`, and `q_<level>` columns.

## Development and validation

```bash
uv sync --locked
uv run pytest
uv build
```

The consumer-facing API instructions are in
[`skills/chronos-forecast-api/SKILL.md`](skills/chronos-forecast-api/SKILL.md).
The Mac Mini bootstrap and production details are in
[`docs/mac-mini-bootstrap.md`](docs/mac-mini-bootstrap.md).
