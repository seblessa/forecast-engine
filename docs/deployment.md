# Forecast Engine deployment

This runbook describes the running Mac Mini topology and the checked-in
templates. It contains no credentials or token values.

```text
Forecasting Studio backend
        │ HTTPS + Bearer token
        ▼
engine.forecasting-studio.com
        │ Cloudflare Tunnel
        ▼
Caddy 127.0.0.1:8080  ── only POST /forecast ──▶  FastAPI :8000
```

## Service configuration

The Forecast Engine process runs from the repository with:

```text
HOST=0.0.0.0
PORT=8000
```

The launchd script sources the private file
`$HOME/.config/forecast-engine.env`, which must contain
`SAAS_API_TOKEN=<secret>` with restrictive file permissions. The token remains
unchanged across deployments.

The service is managed by launchd label
`com.forecast-studio.engine` and starts `server.py` with one Uvicorn process.
The Caddy process uses label `com.forecast-studio.caddy`; the tunnel uses
`com.forecast-studio.cloudflared`.

## Caddy boundary

The tracked [Caddyfile](../infra/Caddyfile) binds only to `127.0.0.1:8080` and
uses Caddy's supported `{$HOME}` substitution for its local storage path:

```text
POST /forecast  →  127.0.0.1:8000
everything else → 404
```

`HOME` is the existing user environment value; no deployment-specific variable
is added for this path.

FastAPI still validates the bearer token. Caddy is an additional path filter,
not the authentication layer. The FastAPI port is never published directly.

## Cloudflare Tunnel

The tracked [cloudflared template](../infra/cloudflared-config.yml.example)
describes the hostname and service target. The active machine-specific file is
intentionally external at:

```text
$HOME/.cloudflared/config.yml
```

It points `engine.forecasting-studio.com` to
`http://127.0.0.1:8080` and ends with a `404` catch-all. The tunnel UUID,
credentials JSON, and Cloudflare certificate are machine/account secrets and
must remain outside Git. A Caddy path change does not require a tunnel restart.

## Restart and inspect

Run these commands on the deployment host from the repository root. After
application code or dependency changes:

```bash
git pull --ff-only
uv sync --locked
launchctl kickstart -k gui/$(id -u)/com.forecast-studio.engine
```

After changing `infra/Caddyfile`, restart Caddy as well:

```bash
launchctl kickstart -k gui/$(id -u)/com.forecast-studio.caddy
```

Do not create a second server or change port `8000`, Caddy port `8080`,
hostname, tunnel, launchd labels, or `SAAS_API_TOKEN`.

## Verification

Local checks on the Mac Mini:

```bash
curl -sS http://127.0.0.1:8000/health
curl -sS http://127.0.0.1:8000/models
curl -sS http://127.0.0.1:8000/docs
curl -sS http://127.0.0.1:8000/openapi.json
```

Authenticated local inference uses the same JSON and token as the public
request. Through the public hostname, only this operation is forwarded:

```bash
curl -i \
  -H 'Authorization: Bearer <SAAS_API_TOKEN>' \
  -H 'Content-Type: application/json' \
  -H 'User-Agent: ForecastStudio-SaaS/1.0' \
  -d '{
    "data": [
      {"date":"2026-01-01T00:00:00Z","dx":1.2,"dy":0.4},
      {"date":"2026-01-01T00:00:01Z","dx":1.3,"dy":0.5}
    ],
    "target_cols":["dx","dy"],
    "forecast_horizon":1,
    "frequency":"s"
  }' \
  https://engine.forecasting-studio.com/forecast
```

The public hostname must return `404` for `/`, `/health`, `/models`, `/docs`,
`/openapi.json`, and any path other than `/forecast`. Missing or invalid
authentication on `/forecast` must return `401` from FastAPI.
