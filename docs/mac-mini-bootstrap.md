# Mac Mini bootstrap

This is one-time setup for the deployment runbook. It creates no tracked
credentials.

## Repository and service secret

Choose a checkout location `<REPO_ROOT>` on the deployment host and ensure the
deployment account can pull `main`:

```bash
git clone https://github.com/seblessa/forecast-engine.git <REPO_ROOT>
cd <REPO_ROOT>
```

Create the private environment file:

```bash
mkdir -p "$HOME/.config"
umask 077
printf '%s\n' 'SAAS_API_TOKEN=<long-random-token>' > "$HOME/.config/forecast-engine.env"
chmod 600 "$HOME/.config/forecast-engine.env"
```

The existing token value is supplied through the Forecasting Studio backend's
secret handoff. Never put it in Git, a URL, shell history, or application logs.

## Cloudflare Tunnel

Authenticate and create the named tunnel with the Cloudflare account owner:

```bash
cloudflared tunnel login
cloudflared tunnel create forecast-engine
cloudflared tunnel route dns forecast-engine engine.forecasting-studio.com
```

Copy [the repository template](../infra/cloudflared-config.yml.example) to
`$HOME/.cloudflared/config.yml`, replace the tunnel UUID, and retain the
generated credentials JSON only in that private directory. The service target
must be `http://127.0.0.1:8080`.

## Services

The API uses FastAPI on port `8000`; Caddy binds to `127.0.0.1:8080`; the
tunnel points to Caddy. Do not forward port `8000` from the router.

For automatic startup, copy the three templates from `infra/launchd/` to
`$HOME/Library/LaunchAgents/`, replace `<REPO_ROOT>` and `<USER_HOME>` in the
copies (and the tunnel UUID in the tunnel plist), then load them:

```bash
mkdir -p "$HOME/Library/Logs" "$HOME/Library/LaunchAgents"
launchctl bootstrap gui/$(id -u) "$HOME/Library/LaunchAgents/com.forecast-studio.engine.plist"
launchctl bootstrap gui/$(id -u) "$HOME/Library/LaunchAgents/com.forecast-studio.caddy.plist"
launchctl bootstrap gui/$(id -u) "$HOME/Library/LaunchAgents/com.forecast-studio.cloudflared.plist"
```

Restart the API after code or dependency changes with:

```bash
launchctl kickstart -k gui/$(id -u)/com.forecast-studio.engine
```

Restart Caddy after changing its configuration. The hostname, tunnel, token,
ports, and launchd labels remain unchanged.
