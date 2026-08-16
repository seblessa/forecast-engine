# Mac Mini bootstrap

This is the one-time setup needed before the deployment runbook can be
executed remotely.

## 1. Allow this computer to use SSH

Run the following on the Mac Mini itself (in a local Terminal or an existing
trusted remote session). Add the public key from the computer that will run
the deployment:

```bash
mkdir -p ~/.ssh
chmod 700 ~/.ssh
printf '%s\n' '<DEPLOYMENT_MACHINE_PUBLIC_KEY>' >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
```

Do not copy a private key. The key must be the `.pub` file only. Confirm the
Mac Mini's SSH host fingerprint before accepting it on the deployment machine.

## 2. Put the repository on the Mac Mini

The deployment machine must be able to pull the intended commit from GitHub,
or the working tree must be copied through the already-authorized SSH session.
Do not put the SaaS token in Git.

## 3. Create the local secret file

On the Mac Mini:

```bash
mkdir -p ~/.config
umask 077
printf '%s\n' 'SAAS_API_TOKEN=<long-random-token>' > ~/.config/forecast-engine.env
chmod 600 ~/.config/forecast-engine.env
```

The token must be shared with the SaaS backend through its secret manager, not
through source control, a URL, or application logs.

## 4. Authenticate Cloudflare on the Mac Mini

Install `cloudflared` on the Mac Mini, then run:

```bash
cloudflared tunnel login
cloudflared tunnel create forecast-engine
cloudflared tunnel route dns forecast-engine engine.forecasting-studio.com
```

Copy [the example tunnel configuration](../infra/cloudflared-config.yml.example)
to `/Users/seb/.cloudflared/config.yml`, replace `<TUNNEL_UUID>`, and run:

```bash
cloudflared tunnel --config /Users/seb/.cloudflared/config.yml run forecast-engine
```

The generated credentials JSON and `cert.pem` stay only in
`/Users/seb/.cloudflared/`; neither belongs in Git.

## 5. Start the services

From the repository on the Mac Mini, use one Uvicorn process:

```bash
set -a
source ~/.config/forecast-engine.env
set +a
HOST=0.0.0.0 PORT=8000 uv run python server.py
```

In another terminal, start Caddy using `infra/Caddyfile`, then start
`cloudflared`. Keep port `8000` un-forwarded on the home router. The public
tunnel must target Caddy on `127.0.0.1:8080`.

For automatic startup after login, copy the three example launchd files from
`infra/launchd/` into `~/Library/LaunchAgents/`, replace the tunnel UUID in
the cloudflared plist, create `~/Library/Logs`, and load them with:

```bash
mkdir -p ~/Library/Logs ~/Library/LaunchAgents
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.forecast-studio.engine.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.forecast-studio.caddy.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.forecast-studio.cloudflared.plist
```

Use `launchctl kickstart -k gui/$(id -u)/com.forecast-studio.engine` to restart
the API after rotating the token. Do not load the cloudflared plist until the
named tunnel and its credentials/configuration exist.
