# Meridian — Alpaca stock paper trading

A local dashboard for Alpaca paper trading in US stocks. Defaults to **SPY**. Python 3.10+; no packages to install. Market prices come from Alpaca's IEX feed, which covers IEX trades rather than the full consolidated US market.

## Run on your Mac

1. Create an Alpaca account, open its **Paper Trading** dashboard, and generate paper API credentials. Keep them private; never paste them into chat or commit them.
2. Download this repository with **Code → Download ZIP**, extract it, and open Terminal inside the extracted folder.
3. Set credentials in that terminal, replacing the example text with your paper keys:

```sh
export APCA_API_KEY_ID='your-paper-api-key'
export APCA_API_SECRET_KEY='your-paper-secret-key'
export ALPACA_SYMBOL='SPY'
python3 server.py
```

4. Open **http://localhost:8000**. Confirm the account and stock, then click **Resume bot**. The app starts paused on every launch. Keep the terminal running. Press Control-C to stop it. Credentials must be set again in a new terminal session. Avoid shared terminals and remove credential-containing commands from shell history.

To use another stock, stop the server, change `ALPACA_SYMBOL` (for example, `AAPL`), and restart. `PORT` overrides port 8000. The server binds only to your computer's loopback interface. The local dashboard has no user authentication; do not expose it publicly.

## What the bot does

- Reads Alpaca paper-account cash, total account equity, selected-stock position, and recent orders every 10 seconds.
- Samples a fresh IEX trade price during regular market hours. The default fast/slow averages cover 5/20 **samples**, not daily candles or one-minute bars. Duplicate trade timestamps are ignored; quiet markets can lengthen warmup. Live data freshness is limited to 30 seconds.
- Waits for the slow window and a subsequent crossover. Bullish crossover: submit a whole-share, market/day **paper** buy using at most approximately 25% of cash (a 1% sizing buffer is included). Bearish crossover: submit a paper sell for the entire selected-stock position. No short selling. Alpaca determines fills, buying-power restrictions, and rejection outcomes.
- Uses fixed `https://paper-api.alpaca.markets` for all trading operations. There is no live-trading endpoint option. The strategy is active only while this process is running and resumed, and only while Alpaca reports regular market hours open.
- Shows account-wide equity and daily equity change (against Alpaca's `last_equity`), selected-stock holdings, signals, and recent selected-stock orders with actual status and filled quantity. Pending orders are not shown as fills. Fees are displayed as unavailable because this order API does not report them.

Use a dedicated paper account: the bot sees existing positions and orders for the selected symbol, including manually created ones. A bearish signal can close that entire position. Pausing prevents new bot orders; it **does not cancel working orders**. Cancel them in Alpaca if needed. Market orders can fill at a different price from the signal. The bot does not install stop-loss or overnight exit orders.

## Persistence and uncertain orders

Strategy settings, the last 200 events, and a pending client-order ID are saved in ignored `data/alpaca-state.json`. API credentials are never saved by the app. Balances/positions/orders are fetched again from Alpaca; historical Bitcoin simulation state is ignored. Charts warm up again after restart or a data gap longer than 30 seconds. Alpaca's newest 100 orders (filtered to the selected stock) are displayed and exportable to CSV; this is not an unlimited audit ledger.

Before submitting an order, the bot durably records a unique client-order ID. After a timeout or restart, it reconciles that ID before allowing further orders. It never blindly retries an uncertain submission. If it cannot find that ID, orders remain blocked. To recover: stop the app, inspect Alpaca's paper dashboard/order history using that exact client-order ID, resolve/cancel any working order, and confirm its final state. Only after verifying that no unresolved submission remains, back up `data/alpaca-state.json` and set its `pending` field to `null`; restart. Do not clear pending state just to bypass an unknown order.

## Troubleshooting

- **Credentials missing / HTTP 401:** use paper keys from the same paper account and restart.
- **Market closed:** the dashboard still reads your account; price sampling and new orders wait until regular hours. Holidays and early closes follow Alpaca's clock.
- **HTTP 403:** check IEX data access, account permissions, or network policy. The app does not require SIP data.
- **Stale trade:** no orders execute from stale prices. Wait for fresh trades in a liquid stock.
- **Rejected order:** check Alpaca's dashboard for account/buying-power/day-trading restrictions. No automatic resubmission.

Cloud environments need HTTPS access to `paper-api.alpaca.markets` and `data.alpaca.markets`. A local Mac normally only needs an Internet connection. No credentials are needed to render the dashboard, but account/data checks and paper orders require them.

## Validate

```sh
python3 -m unittest discover -s tests -v
node --check static/app.js  # optional; requires Node.js
```

Tests use a fake Alpaca adapter, not a real account. They cover paper-only configuration, missing credentials, account synchronization, crossover submission, closed/stale markets, sizing, working-order suppression, uncertain submissions, and reconciliation, plus strategy arithmetic. End-to-end authenticated data and order execution must be checked in your paper account.
