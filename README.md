# Meridian

A Bitcoin paper-trading dashboard with a moving-average crossover strategy. Python 3.10+; no application dependencies or API keys required.

## Run

```sh
cd /workspace/trading-bot
python server.py
```

The HTTP server listens on port 8000 (override with `PORT`). The browser dashboard is served at `/`; JSON state is available at `/api/state`. Keep this development server on a trusted network: it has no authentication.

## Strategy

Coinbase BTC-USD spot prices are polled every 10 seconds. Default moving averages use the latest 5 and 20 samples, not daily candles. The bot waits for a complete slow window and a subsequent crossover. A bullish crossover buys BTC with 25% of available paper cash; a bearish crossover closes the entire position. Long only, one position at a time, starting with $10,000 simulated cash. Every fill includes a 0.10% simulated fee. Fills assume the observed spot price without slippage or order-book liquidity.

Use the dashboard to pause/resume orders, edit windows, inspect all signals and fills, and export recent trades to CSV. Pausing keeps market monitoring active. Resuming or editing windows establishes a new baseline before trading. Data gaps longer than 30 seconds clear the moving-average history and require warmup again.

Balances, settings, and the most recent 200 trades/events and 360 price samples persist atomically in ignored `data/state.json`. These are bounded histories, not a permanent audit ledger. The live feed must recover after each process restart before new orders execute. Never submits real exchange orders.

## Network

Allow HTTPS to `api.coinbase.com` in environment settings. If blocked or unavailable, the app explicitly shows the failed feed and places no orders. It does not substitute simulated prices. After saving network settings, publish the environment configuration as required by the cloud UI. Browser fonts are optional; local fallback fonts work offline.

## Validate

```sh
python -m unittest discover -s tests -v
node --check static/app.js
```

Tests cover both crossover directions, cash/position/fee accounting, pause, warmup after feed gaps, invalid settings, and duplicate-position prevention.
