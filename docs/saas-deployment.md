# SaaS deployment runbook

This runbook describes the deployed v1/v2 topology. The FastAPI process runs on
the Mac Mini at home. Caddy filters the local public-ingress port, and an
outbound HTTPS tunnel publishes only the three authenticated SaaS paths.

## Local server

Run one server process and keep the port private to the home network:

```bash
SAAS_API_TOKEN='<secret>' HOST=0.0.0.0 PORT=8000 uv run python server.py
```

Do not commit the token or place it in a tracked file. Prefer the Mac Mini's
service or secret configuration to an interactive shell history entry.

Do not configure router port forwarding for port `8000`. Local clients can use
the Mac Mini's LAN hostname or address, for example:

```text
http://mac-mini.local:8000/docs
http://mac-mini.local:8000/forecast
```

## Public-ingress filter

Run Caddy with the checked-in [Caddyfile](../infra/Caddyfile):

```bash
caddy run --config /path/to/forecast-engine/infra/Caddyfile
```

Caddy listens only on `127.0.0.1:8080`, forwards the three SaaS paths to
FastAPI's private port, and returns `404` for every other path. The tunnel must
target `http://127.0.0.1:8080`, never `http://127.0.0.1:8000`.

## Public hostname

Create the DNS and tunnel/reverse-proxy configuration for:

```text
engine.forecasting-studio.com
```

The public ingress must forward only these exact paths to the local FastAPI
server:

```text
/v1/saas/forecast      → http://127.0.0.1:8000/v1/saas/forecast
/v1/saas/forecast/csv  → http://127.0.0.1:8000/v1/saas/forecast/csv
/v2/saas/forecast      → http://127.0.0.1:8000/v2/saas/forecast
```

When using the checked-in Caddy filter, configure the tunnel hostname
`engine.forecasting-studio.com` to target:

```text
http://127.0.0.1:8080
```

The default route must return `404`. Do not publish `/docs`, `/openapi.json`,
`/health`, `/models`, `/forecast`, `/forecast/csv`, or private `/v2/forecast`
through the public ingress. The private v2 and model-capability routes remain
available on the FastAPI port for trusted local consumers.

The checked-in files describe the reusable deployment shape:

- `infra/Caddyfile` is the exact public path allowlist used by Caddy.
- `infra/cloudflared-config.yml.example` is a secret-free tunnel template.
- `infra/launchd/` contains the service templates and engine start script.

The live Mac Mini keeps machine-specific material outside Git: launchd copies
live under `/Users/seb/Library/LaunchAgents/`, the Cloudflare config is
`/Users/seb/.cloudflared/config.yml`, generated tunnel credentials remain in
that directory, and `/Users/seb/.config/forecast-engine.env` contains the
`SAAS_API_TOKEN` value. The service source is still the checked-out repository.

An outbound tunnel is preferred because it does not require exposing the home
router or the FastAPI port. The exact DNS record and tunnel command depend on
the provider managing `forecasting-studio.com`; this repository deliberately does
not include provider credentials or a provider-specific secret.

For Cloudflare Tunnel, create a named tunnel and configure it with the
checked-in [cloudflared template](../infra/cloudflared-config.yml.example).
Create a published application for `engine.forecasting-studio.com` whose service
is `http://127.0.0.1:8080`. A Cloudflare-managed tunnel uses a CNAME to the
tunnel's `cfargotunnel.com` hostname; the DNS and tunnel are separate
configuration steps.

On the Mac Mini, run the tunnel with one process and the generated credentials:

```bash
cloudflared tunnel --config /Users/seb/.cloudflared/config.yml run <TUNNEL_NAME_OR_UUID>
```

The UUID, credentials file, and any account certificate are Cloudflare-managed
secrets and must stay outside Git.

## Smoke tests

From outside the home network:

```bash
curl -i https://engine.forecasting-studio.com/v1/saas/forecast
```

Expected result: `401`.

The generic public route requires the same token:

```bash
curl -i https://engine.forecasting-studio.com/v2/saas/forecast
```

Expected result: `401`.

With the token:

```bash
curl -i \
  -H 'Authorization: Bearer <SAAS_API_TOKEN>' \
  -H 'Content-Type: application/json' \
  -d '{
    "data": [
      {"date": "2025-01-01T00:00:00Z", "target": 84.2},
      {"date": "2025-01-01T01:00:00Z", "target": 86.1}
    ],
    "forecast_horizon": 1,
    "frequency": "h",
    "engine": "chronos2"
  }' \
  https://engine.forecasting-studio.com/v1/saas/forecast
```

From outside the home network, each of these must return `404` or `403`:

```text
https://engine.forecasting-studio.com/forecast
https://engine.forecasting-studio.com/forecast/csv
https://engine.forecasting-studio.com/docs
https://engine.forecasting-studio.com/health
https://engine.forecasting-studio.com/models
https://engine.forecasting-studio.com/openapi.json
https://engine.forecasting-studio.com/v2/forecast
```

From inside the home network, verify the private service directly:

```text
GET  http://127.0.0.1:8000/health
GET  http://127.0.0.1:8000/models
POST http://127.0.0.1:8000/v2/forecast
GET  http://127.0.0.1:8000/docs
GET  http://127.0.0.1:8000/openapi.json
```

The launchd labels are `com.forecast-studio.engine`,
`com.forecast-studio.caddy`, and `com.forecast-studio.cloudflared`. Restart
the API after code or dependency changes with:

```bash
launchctl kickstart -k gui/$(id -u)/com.forecast-studio.engine
```

After changing `infra/Caddyfile`, restart only Caddy:

```bash
launchctl kickstart -k gui/$(id -u)/com.forecast-studio.caddy
```

The Cloudflare process does not need a restart for an application path change;
its hostname and service target remain unchanged.
