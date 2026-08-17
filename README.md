# Forecast Engine

Forecast Engine is a reusable Python package and a thin authenticated FastAPI
service for time-series forecasting with the official Amazon Chronos
pipelines.

The product has one forecasting contract:

```text
ForecastEngine Python API
POST /forecast
```

The Python core owns data normalization, validation, model capabilities,
pipeline caching, inference, and the canonical response. FastAPI only handles
JSON transport and bearer authentication.

## Installation

The package is prepared for PyPI publication but is not published yet. For
local development:

```bash
uv sync --locked
```

Future PyPI installation:

```bash
pip install forecast-engine
```

To install the optional HTTP service dependencies from a published package:

```bash
pip install 'forecast-engine[server]'
```

## Python API

```python
import pandas as pd

from forecast_engine import ForecastEngine

engine = ForecastEngine()
data = pd.DataFrame(
    {
        "date": pd.date_range("2026-01-01", periods=24, freq="h"),
        "sales": range(24),
    }
)

result = engine.forecast(
    data=data,
    target_cols=["sales"],
    forecast_horizon=24,
    datetime_col="date",
    frequency="h",
)
records = result.to_records()
```

Related variables are forecast jointly by Chronos 2:

```python
result = engine.forecast(
    data=movement_history,
    target_cols=["dx", "dy"],
    forecast_horizon=8,
    datetime_col="date",
    frequency="s",
)
```

`ForecastResult.to_records()` returns long-format records with `timestamp`,
`item_id`, `target_name`, `prediction`, and `quantiles`. Timestamps are UTC
ISO 8601 values with a `Z` suffix, such as
`2026-01-01T00:00:03Z`. Append a returned timestamp directly to the next
input context; the client must not add `Z` or convert timezones.

## REST API

Start the local service with:

```bash
SAAS_API_TOKEN='<secret>' HOST=0.0.0.0 PORT=8000 uv run python server.py
```

The only inference operation is:

```http
POST /forecast
Authorization: Bearer <SAAS_API_TOKEN>
Content-Type: application/json
```

Example:

```json
{
  "data": [
    {"date": "2026-01-01T00:00:00Z", "dx": 1.2, "dy": 0.4},
    {"date": "2026-01-01T00:00:01Z", "dx": 1.3, "dy": 0.5},
    {"date": "2026-01-01T00:00:02Z", "dx": 1.4, "dy": 0.6}
  ],
  "target_cols": ["dx", "dy"],
  "forecast_horizon": 5,
  "datetime_col": "date",
  "item_id_col": null,
  "frequency": "s",
  "model": "chronos2",
  "future_data": null,
  "quantile_levels": [0.1, 0.5, 0.9],
  "batch_size": 256,
  "context_length": null,
  "cross_learning": false
}
```

Response:

```json
{
  "predictions": [
    {
      "timestamp": "2026-01-01T00:00:03Z",
      "item_id": null,
      "target_name": "dx",
      "prediction": 1.25,
      "quantiles": {"0.1": 1.0, "0.5": 1.25, "0.9": 1.5}
    }
  ]
}
```

The endpoint requires the existing `SAAS_API_TOKEN` as a bearer token. Keep
the token in the Forecasting Studio backend secret store; browser code must
never receive it. Missing or invalid credentials return `401`.

The request fields are:

- `data`: structured historical records containing the datetime and targets.
- `target_cols`: one or more related variables for the same forecasting task.
- `forecast_horizon`: positive number of future steps.
- `datetime_col`: datetime field, default `date`.
- `item_id_col`: optional field identifying separate items/tasks.
- `frequency`: pandas frequency, for example `s`, `h`, or `D`.
- `model`: configured model name, default `chronos2`.
- `future_data`: optional known future records with the same item structure.
- `quantile_levels`: requested probabilities between zero and one.
- `batch_size`, `context_length`, `cross_learning`: model runtime controls.

Historical covariates are additional columns in `data`. Known future
covariates are supplied through `future_data`. The same contract supports one
item or many items and one target or many targets.

Administrators can inspect available model capabilities without loading
weights through the local-only endpoint:

```http
GET http://localhost:8000/models
```

The configured names are `chronos2` and `chronos-bolt-base`. `/models` is an
operational source of truth for local Engine administrators; Forecasting Studio
must not call `/models` through the public hostname. The public ingress exposes
only `POST /forecast`. The endpoint reports whether each model supports
multivariate data, covariates, panel items, cross-learning, and context length.
Chronos Bolt accepts one target and no covariates; Chronos 2 supports the
multivariate and covariate use cases.

Local operational routes are `GET /health`, `GET /models`, `GET /docs`, and
`GET /openapi.json`. They are not published through the public hostname.

## Development

Run the complete validation suite:

```bash
uv run pytest -W error
uv build
```

`uv build` creates both a wheel and a source distribution. The wheel contains
the importable `forecast_engine` package; the FastAPI service entrypoint is
kept in the repository for deployment.

## Repository layout

```text
forecast_engine/
    core.py             # reusable Python API and ForecastResult
    models.py           # model registry and capabilities
    pipeline.py         # lazy pipeline loading and cache
    errors.py            # public validation/inference errors
    api/                # FastAPI schemas, auth, and routes
server.py              # Uvicorn entrypoint
tests/                 # core and HTTP contract tests
docs/                  # API, integration, deployment, and bootstrap guides
infra/                 # Caddy, Cloudflare template, and launchd templates
```

## Production overview

Forecasting Studio calls
`https://engine.forecasting-studio.com/forecast` server-to-server with the
same bearer token. Cloudflare Tunnel points to Caddy on `127.0.0.1:8080`;
Caddy forwards only `/forecast` to FastAPI on private port `8000`. launchd
keeps the Forecast Engine, Caddy, and tunnel processes running. See
[the API contract](docs/api.md), [the Forecasting Studio handoff](docs/forecast-studio-integration.md),
and [the deployment runbook](docs/deployment.md).

## License

Apache License 2.0. See [LICENSE](LICENSE).
