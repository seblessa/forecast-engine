# Mac Mini bootstrap

This is one-time setup for the deployment runbook. It creates no tracked
credentials.

## SSH access

On the Mac Mini, add the deployment machine's public key to the account used
for service management:

```bash
mkdir -p ~/.ssh
chmod 700 ~/.ssh
printf '%s\n' '<DEPLOYMENT_MACHINE_PUBLIC_KEY>' >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
```

Copy only the `.pub` file, never a private key. Confirm the Mac Mini SSH host
fingerprint before accepting it.

## Repository and service secret

Clone the repository at `/Users/seb/Projects/forecast-engine` and ensure the
deployment account can pull `main`. Create the private environment file:

```bash
mkdir -p ~/.config
umask 077
printf '%s\n' 'SAAS_API_TOKEN=<long-random-token>' > ~/.config/forecast-engine.env
chmod 600 ~/.config/forecast-engine.env
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
`/Users/seb/.cloudflared/config.yml`, replace the tunnel UUID, and retain the
generated credentials JSON only in that private directory. The service target
must be `http://127.0.0.1:8080`.

## Services

The API uses FastAPI on port `8000`; Caddy binds to `127.0.0.1:8080`; the
tunnel points to Caddy. Do not forward port `8000` from the router.

For automatic startup, copy the three templates from `infra/launchd/` to
`~/Library/LaunchAgents/`, replace the tunnel UUID in the tunnel plist, and
load them:

```bash
mkdir -p ~/Library/Logs ~/Library/LaunchAgents
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.forecast-studio.engine.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.forecast-studio.caddy.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.forecast-studio.cloudflared.plist
```

Restart the API after code or dependency changes with:

```bash
launchctl kickstart -k gui/$(id -u)/com.forecast-studio.engine
```

Restart Caddy after changing its configuration. The hostname, tunnel, token,
ports, and launchd labels remain unchanged.
