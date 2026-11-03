# Run Meridian on an always-on Ubuntu VPS

The VPS runs the bot independently of your Mac. Docker starts it after crashes or server reboots and retains strategy settings and pending order IDs in a named volume. The dashboard stays private: SSH forwards it to your browser when you want to look. Closing the SSH tunnel or your Mac does not stop the bot.

## 1. Create a server

Create an Ubuntu 24.04 LTS VPS with at least 1 shared CPU, 1 GB RAM, and 10 GB disk at your chosen provider. Enable SSH-key authentication. Allow inbound SSH (TCP 22) from your IP in the provider firewall. Do not open port 8000. Allow outbound HTTPS for Alpaca. Provider charges apply; this repository does not provision a server.

Install Docker Engine and the Compose plugin using Docker's official Ubuntu instructions:
https://docs.docker.com/engine/install/ubuntu/

The commands below assume your SSH user can run Docker. If it cannot, prefix Docker commands with `sudo`. Keep Docker enabled at boot (`sudo systemctl enable --now docker`).

## 2. Download and configure on the VPS

From your Mac:

```sh
ssh YOUR_USER@YOUR_SERVER_IP
```

On the VPS (install Git with `sudo apt-get update` then `sudo apt-get install -y git` if needed):

```sh
git clone https://github.com/Swapnil1029/trading-bot.git
cd trading-bot
cp deploy/paper.env.example .env
chmod 600 .env
nano .env
```

Enter your Alpaca **paper** key ID and secret in `.env`, save, and exit. Keep the file private. Do not paste keys into chat. Use a dedicated paper account. `ALPACA_SYMBOL` defaults to SPY. `RESUME_ON_RESTART=true` lets the server restore a previously enabled bot; first launch is paused. A previously paused bot stays paused. Setting it to false makes every restart start paused. Keys are read only when the container starts, so recreate it after key changes.

**Before enabling this deployment, stop the old bot on your Mac with Control-C.** Do not run multiple bot processes against the same paper account/symbol. Independent instances can submit conflicting orders.

## 3. Start and verify

On the VPS:

```sh
docker compose up -d --build
docker compose ps
docker compose exec bot python3 check_connection.py
docker compose logs --tail=50 bot
```

All three connection checks should report OK. These checks do not place orders. Market data can be available when regular trading is closed. The bot itself waits for regular market hours and fresh prices.

On your Mac, in a separate terminal:

```sh
ssh -N -L 8000:127.0.0.1:8000 YOUR_USER@YOUR_SERVER_IP
```

Open http://localhost:8000. If local port 8000 is occupied, forward `8002:127.0.0.1:8000` instead, and open http://localhost:8002. Review the account and symbol, then click **Resume bot**. You may close this SSH terminal afterwards; the VPS continues running. The bot waits for warmup and a new crossover before sending orders. Its strategy remains regular-hours only even though the process runs around the clock.

## 4. Updates, restart, and stop

On the VPS, from the checkout:

```sh
# Update code and recreate the service; persistent state is retained.
git pull --ff-only
docker compose up -d --build

# Restart without updating code.
docker compose restart bot

# Stop the bot, retaining state.
docker compose stop bot
```

Pausing in the dashboard stops new bot orders, but **does not cancel existing Alpaca orders**. Stopping Docker also does not cancel submitted orders or close positions. Inspect Alpaca directly when necessary. Never use `docker compose down -v` unless intentionally deleting all stored state; losing pending IDs can break uncertain-order reconciliation.

## 5. Operational limits

This is a single-server deployment, not a high-availability service. A VPS outage, Internet failure, suspended account, or unreconciled order can stop trading. Docker restarts exited processes; it does not detect every stalled process or replace external monitoring. Review the account regularly. Configure a provider uptime alert for the VPS; keep the dashboard port private. The app has no public login, so do not expose it through a public reverse proxy without adding authentication and HTTPS first.

If moving an existing instance with an unresolved order, resolve its status in Alpaca first. Do not run two copies or discard its pending state to work around an unknown submission. The default setup starts a new server-side journal, while Alpaca balances and orders are fetched from your existing paper account. Back up the Docker volume before planned migrations. Local Mac data is not uploaded automatically.
