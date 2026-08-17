# Forecast Engine

![Python](https://img.shields.io/badge/Python-3.10--3.13-blue)
![License](https://img.shields.io/badge/License-Apache%202.0-green)
![Amazon Chronos](https://img.shields.io/badge/Amazon-Chronos-ff9900)

**A lightweight forecasting engine built on the official Amazon Chronos pipelines.**

Forecast Engine provides one clean interface for running modern time-series forecasts from Python or over HTTP. It supports univariate and multivariate forecasting, panel data, covariates, prediction intervals, and reusable model pipelines without exposing Chronos internals to the application layer.

```text
Python  →  ForecastEngine.forecast(...)
HTTP    →  POST /forecast
```

Built on [amazon-science/chronos-forecasting](https://github.com/amazon-science/chronos-forecasting).

## Why Forecast Engine?

The official Chronos package provides the forecasting models. Forecast Engine adds the application layer around them:

- **Chronos 2 native multivariate forecasting** for related targets such as `dx + dy`.
- **Univariate forecasting** with Chronos 2 or Chronos Bolt.
- **Panel forecasting** for multiple independent items in one request.
- **Historical and known-future covariates** with Chronos 2.
- **Configurable quantiles** for prediction intervals.
- **Stable validation and response formats** across Python and HTTP usage.
- **Lazy model loading and pipeline reuse** so model weights are not reloaded for every forecast.
- **A single authenticated REST endpoint** that is easy to place behind an application backend.

## Quick start

The package is prepared for PyPI but is **not published there yet**.

For now, clone the repository and install the locked environment:

```bash
git clone https://github.com/seblessa/forecast-engine.git
cd forecast-engine
uv sync --locked
```

### Python

```python
import pandas as pd

from forecast_engine import ForecastEngine

series = pd.DataFrame({
    "date": pd.date_range("2026-01-01", periods=48, freq="h"),
    "sales": range(48),
})

engine = ForecastEngine()

result = engine.forecast(
    data=series,
    target_cols=["sales"],
    forecast_horizon=12,
    frequency="h",
)

print(result.to_records())
```

For related variables, pass them together:

```python
result = engine.forecast(
    data=movement_history,
    target_cols=["dx", "dy"],
    forecast_horizon=8,
    frequency="s",
)
```

Chronos 2 receives those targets jointly in one native multivariate forecast.

## REST API

Forecast Engine also includes a thin FastAPI service. The public inference contract is intentionally small:

```http
POST /forecast
Authorization: Bearer <token>
Content-Type: application/json
```

Example request body:

```json
{
  "data": [
    {"date": "2026-01-01T00:00:00Z", "dx": 1.2, "dy": 0.4},
    {"date": "2026-01-01T00:00:01Z", "dx": 1.3, "dy": 0.5},
    {"date": "2026-01-01T00:00:02Z", "dx": 1.4, "dy": 0.6}
  ],
  "target_cols": ["dx", "dy"],
  "forecast_horizon": 5,
  "frequency": "s",
  "model": "chronos2"
}
```

Responses use a stable long format with:

```text
timestamp · item_id · target_name · prediction · quantiles
```

Timestamps are returned as explicit UTC ISO 8601 values ending in `Z` and can be reused directly in later requests.

See the [API reference](docs/api.md) for the complete request contract, validation rules, errors, covariates, panel data, and runtime options.

## Models

| Model | Multivariate | Covariates | Panel data | Best for |
|---|---:|---:|---:|---|
| `chronos2` | Yes | Yes | Yes | General forecasting, related targets, covariates |
| `chronos-bolt-base` | No | No | Yes | Fast univariate forecasting |

`chronos2` is the default model.

## Documentation

The README intentionally stays small. More detailed documentation lives in [`docs/`](docs/README.md):

- [API contract](docs/api.md)
- [Forecasting Studio integration](docs/forecast-studio-integration.md)
- [Deployment](docs/deployment.md)
- [Mac Mini bootstrap](docs/mac-mini-bootstrap.md)

## Development

```bash
uv sync --locked
uv run pytest -W error
uv build
```

`uv build` produces both a wheel and a source distribution. A future PyPI release will support:

```bash
pip install forecast-engine
pip install "forecast-engine[server]"
```

## License

Licensed under the [Apache License 2.0](LICENSE).
