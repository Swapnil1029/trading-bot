import json
import os
import threading
import time
import urllib.request
from collections import deque
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).parent
DATA = ROOT / 'data' / 'state.json'


class Bot:
    def __init__(self, persist=True):
        self.lock = threading.RLock()
        self.persist = persist
        self.running = True
        self.short, self.long = 5, 20
        self.cash, self.qty = 10000.0, 0.0
        self.cost = 0.0
        self.realized = 0.0
        self.prices = deque(maxlen=360)
        self.events = deque(maxlen=200)
        self.trades = deque(maxlen=200)
        self.regime = None
        self.feed = 'Connecting'
        self.error = None
        self.last_tick = 0
        if persist and DATA.exists():
            state = json.loads(DATA.read_text())
            for key in ('cash', 'qty', 'cost', 'realized', 'short', 'long', 'running', 'regime', 'last_tick'):
                if key in state:
                    setattr(self, key, state[key])
            self.prices.extend(state.get('prices', []))
            self.events.extend(state.get('events', []))
            self.trades.extend(state.get('trades', []))

    def event(self, kind, message):
        self.events.appendleft({'time': time.time(), 'kind': kind, 'message': message})

    def save(self):
        if self.persist:
            DATA.parent.mkdir(exist_ok=True)
            tmp = DATA.with_suffix('.tmp')
            tmp.write_text(json.dumps(self.snapshot()))
            tmp.replace(DATA)

    def snapshot(self):
        with self.lock:
            price = self.prices[-1]['price'] if self.prices else None
            equity = self.cash + self.qty * (price or 0)
            return dict(cash=self.cash, qty=self.qty, cost=self.cost, realized=self.realized,
                        equity=equity, pnl=equity - 10000, running=self.running,
                        short=self.short, long=self.long, regime=self.regime,
                        prices=list(self.prices), events=list(self.events), trades=list(self.trades),
                        feed=self.feed, error=self.error, last_tick=self.last_tick,
                        symbol='BTC / USD', interval=10, fee_rate=0.001)

    def tick(self, price, timestamp=None):
        with self.lock:
            now = timestamp or time.time()
            # Never trade across a feed interruption; rebuild the signal baseline.
            if self.last_tick and now - self.last_tick > 30:
                self.prices.clear()
                self.regime = None
                self.event('FEED', 'Feed resumed. Rebuilding moving-average history.')
            self.last_tick = now
            self.feed, self.error = 'Live', None
            self.prices.append({'time': now, 'price': price})
            values = [p['price'] for p in self.prices]
            if len(values) >= self.long:
                fast = sum(values[-self.short:]) / self.short
                slow = sum(values[-self.long:]) / self.long
                regime = 1 if fast > slow else -1 if fast < slow else 0
                previous = self.regime
                if regime and previous and regime != previous:
                    side = 'BUY' if regime > 0 else 'SELL'
                    self.event('SIGNAL', f'{side} crossover · SMA {self.short} crossed {"above" if regime > 0 else "below"} SMA {self.long}')
                    if self.running:
                        self.execute(side, price, now)
                if regime:
                    self.regime = regime
            self.save()

    def execute(self, side, price, now):
        if side == 'BUY' and not self.qty:
            spend = self.cash * 0.25
            fee = spend * 0.001
            qty = (spend - fee) / price
            self.cash -= spend
            self.qty, self.cost = qty, spend
        elif side == 'SELL' and self.qty:
            qty = self.qty
            gross = qty * price
            fee = gross * 0.001
            self.cash += gross - fee
            self.realized += gross - fee - self.cost
            self.qty, self.cost = 0, 0
        else:
            self.event('HOLD', 'No order: position already open.' if side == 'BUY' else 'No order: no BTC to sell.')
            return
        self.trades.appendleft(dict(time=now, side=side, price=price, qty=qty, fee=fee, value=qty * price))
        self.event(side, f'Paper {side.lower()} · {qty:.6f} BTC at ${price:,.2f} · fee ${fee:.2f}')

    def configure(self, payload):
        with self.lock:
            if 'short' in payload or 'long' in payload:
                short, long = payload.get('short', self.short), payload.get('long', self.long)
                if type(short) is not int or type(long) is not int or not 2 <= short < long <= 120:
                    raise ValueError('Use whole-number windows: 2 ≤ fast < slow ≤ 120.')
                self.short, self.long, self.regime = short, long, None
                self.event('CONFIG', f'Strategy updated · SMA {short} / {long}. Waiting for a new crossover.')
            if 'running' in payload:
                if type(payload['running']) is not bool:
                    raise ValueError('running must be a boolean')
                self.running = payload['running']
                self.regime = None
                self.event('BOT', 'Paper trading resumed. Waiting for a new crossover.' if self.running else 'Paper trading paused. Market monitoring continues.')
            self.save()


class StockBot(Bot):
    """Paper account state is authoritative; local files hold only strategy/journal state."""
    def __init__(self, persist=True, client=None):
        from alpaca import Alpaca
        super().__init__(persist=False)
        self.persist = persist
        self.client = client or Alpaca()
        self.symbol = os.getenv('ALPACA_SYMBOL', 'SPY').upper()
        import re
        if not re.fullmatch(r'[A-Z][A-Z0-9.]{0,9}', self.symbol):
            raise ValueError('ALPACA_SYMBOL must be a US stock ticker such as SPY or AAPL.')
        self.running = False
        self.cash = self.equity = self.qty = self.cost = self.pnl = 0.0
        self.pending = None
        self.market_open = False
        self.account_ready = False
        self.position_value = 0.0
        self.next_open = None
        self.last_trade_time = 0.0
        self.blocked = True
        if persist and STOCK_DATA.exists():
            saved = json.loads(STOCK_DATA.read_text())
            if saved.get('symbol') == self.symbol:
                self.short, self.long = saved.get('short', 5), saved.get('long', 20)
                self.events.extend(saved.get('events', []))
            # An unresolved submission is reconciled even if the selected ticker changes.
            self.pending = saved.get('pending')
        self.event('BOT', f'{self.symbol} · Alpaca paper mode. Start paused; resume after reviewing your account.')

    def snapshot(self):
        with self.lock:
            return dict(cash=self.cash, equity=self.equity, qty=self.qty, cost=self.cost,
                        position_value=self.position_value, pnl=self.pnl, realized=None,
                        running=self.running, short=self.short, long=self.long, regime=self.regime,
                        prices=list(self.prices), events=list(self.events), trades=list(self.trades),
                        feed=self.feed, error=self.error, last_tick=self.last_tick,
                        symbol=self.symbol, interval=10, fee_rate=None,
                        market_open=self.market_open, next_open=self.next_open,
                        account_ready=self.account_ready, pending=self.pending)

    def save(self):
        if self.persist:
            STOCK_DATA.parent.mkdir(exist_ok=True)
            temp = STOCK_DATA.with_suffix('.tmp')
            temp.write_text(json.dumps(dict(symbol=self.symbol, short=self.short, long=self.long,
                                           events=list(self.events), pending=self.pending)))
            temp.replace(STOCK_DATA)

    def reconcile(self):
        if not self.pending:
            return
        from urllib.parse import quote
        order = self.client.request('/v2/orders:by_client_order_id?client_order_id=' + quote(self.pending, safe=''))
        if order is None:
            raise ValueError('An earlier submission has uncertain status. Orders are blocked. Inspect the Alpaca paper account and follow README recovery instructions.')
        terminal = {'filled', 'canceled', 'expired', 'rejected', 'replaced', 'done_for_day'}
        if order['status'] in terminal:
            self.event('ORDER', f"Order {order['client_order_id']} · {order['status']} · filled {order.get('filled_qty', '0')} shares")
            self.pending = None
            self.save()

    def refresh(self):
        from datetime import datetime
        with self.lock:
            self.reconcile()
            account = self.client.request('/v2/account')
            positions = self.client.request('/v2/positions')
            orders = self.client.request('/v2/orders?status=all&limit=100&direction=desc')
            clock = self.client.request('/v2/clock')
            asset = self.client.request('/v2/assets/' + self.symbol)
            if not account or positions is None or orders is None or not clock or not asset:
                raise ValueError('Alpaca returned incomplete account or asset data.')
            if not asset.get('tradable') or asset.get('class') != 'us_equity':
                raise ValueError('Select a tradable US equity ticker in ALPACA_SYMBOL and restart.')
            self.cash = float(account['cash'])
            self.equity = float(account['equity'])
            self.pnl = self.equity - float(account['last_equity'])
            self.buying_power = float(account['buying_power'])
            self.blocked = bool(account.get('trading_blocked') or account.get('account_blocked') or account.get('trade_suspended_by_user')) or account.get('status') != 'ACTIVE'
            pos = next((p for p in positions if p['symbol'] == self.symbol), None)
            self.qty = float(pos['qty']) if pos else 0.0
            self.cost = float(pos['cost_basis']) if pos else 0.0
            self.position_value = float(pos['market_value']) if pos else 0.0
            # Check all open orders separately; recent history can omit older working orders.
            open_orders = self.client.request('/v2/orders?status=open&limit=500')
            if open_orders is None:
                raise ValueError('Could not verify working orders.')
            self.has_open_order = any(o['symbol'] == self.symbol for o in open_orders)
            self.market_open = bool(clock['is_open'])
            self.next_open = clock.get('next_open')
            def order_time(o):
                return datetime.fromisoformat(o['submitted_at'].replace('Z', '+00:00')).timestamp()
            self.trades.clear()
            for o in orders:
                if o['symbol'] != self.symbol:
                    continue
                self.trades.append(dict(time=order_time(o), side=o['side'].upper(),
                                        price=float(o['filled_avg_price']) if o.get('filled_avg_price') else None,
                                        qty=float(o.get('filled_qty') or 0), fee=None,
                                        status=o['status'], id=o['id'], client_order_id=o.get('client_order_id')))
            self.account_ready = True
            if self.blocked:
                raise ValueError('Alpaca account is not active or trading is blocked. Review your paper account.')
            if not self.market_open:
                self.feed = 'Market closed'
                self.error = None
                self.regime = None
                self.prices.clear()
                self.save()
                return
            latest = self.client.latest(self.symbol)
            trade = (latest or {}).get('trade')
            if not trade:
                raise ValueError('No IEX trade available for the selected stock.')
            stamp = datetime.fromisoformat(trade['t'].replace('Z', '+00:00')).timestamp()
            now = time.time()
            price = float(trade['p'])
            import math
            if not math.isfinite(price) or price <= 0 or not -5 <= now - stamp <= 30:
                raise ValueError('IEX trade is stale or invalid. Waiting for fresh market data; orders disabled.')
            if stamp <= self.last_trade_time:
                if now - self.last_tick > 30:
                    raise ValueError('No fresh IEX trade. Orders disabled until the feed recovers.')
                return
            self.last_trade_time = stamp
            self.tick(price, now)

    def execute(self, side, price, now):
        import uuid
        if self.pending or self.has_open_order:
            self.event('HOLD', 'An order is still working or being reconciled; no new order sent.')
            return
        if self.blocked or not self.market_open or self.qty < 0:
            self.event('HOLD', 'Account, market, or existing short position prevents an order.')
            return
        if side == 'BUY' and self.qty == 0:
            import math
            quantity = math.floor(min(max(self.cash, 0) * 0.25, self.buying_power) / (price * 1.01))
            if quantity < 1:
                self.event('HOLD', 'Insufficient cash allocation for one whole share.')
                return
        elif side == 'SELL' and self.qty > 0:
            quantity = self.qty
        else:
            self.event('HOLD', 'Position already open.' if side == 'BUY' else 'No shares to sell.')
            return
        self.pending = 'meridian-' + uuid.uuid4().hex
        self.save()  # Durable intent BEFORE submission; never retry an uncertain POST.
        self.event('ORDER', f'Submitting paper {side} · {quantity:g} {self.symbol} · {self.pending}')
        order = self.client.request('/v2/orders', method='POST', body=dict(
            symbol=self.symbol, qty=str(quantity), side=side.lower(), type='market',
            time_in_force='day', client_order_id=self.pending))
        if not order:
            raise ValueError('Order submission uncertain; reconciliation required.')
        self.event('ORDER', f"Alpaca paper order {order['id']} · {order['status']}")
        self.save()


STOCK_DATA = ROOT / 'data' / 'alpaca-state.json'


def poll(bot):
    while True:
        try:
            bot.refresh()
        except Exception as exc:
            with bot.lock:
                from alpaca import AlpacaError
                message = str(exc) if isinstance(exc, (AlpacaError, ValueError)) else 'Alpaca response could not be processed. Orders disabled; inspect your paper account.'
                if bot.feed != 'Unavailable' or bot.error != message:
                    bot.event('FEED', message)
                bot.feed, bot.error = 'Unavailable', message
                bot.regime = None
                bot.save()
        time.sleep(10)


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT / 'static'), **kwargs)

    def send_json(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == '/api/state':
            return self.send_json(self.server.bot.snapshot())
        return super().do_GET()

    def do_POST(self):
        origin = self.headers.get('Origin')
        host = self.headers.get('Host', '')
        if (origin and origin != 'http://' + host) or self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
            return self.send_json({'error': 'Same-origin JSON requests only'}, 403)
        if self.path != '/api/config':
            return self.send_json({'error': 'Not found'}, 404)
        try:
            length = int(self.headers.get('Content-Length', 0))
            if not 0 < length <= 4096:
                raise ValueError('Invalid request size')
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ValueError('Expected an object')
            self.server.bot.configure(payload)
            self.send_json(self.server.bot.snapshot())
        except (ValueError, TypeError) as exc:
            self.send_json({'error': str(exc)}, 400)


if __name__ == '__main__':
    bot = StockBot()
    bot.event('BOT', 'Dashboard connected. Paper trading only; no real orders.')
    server = ThreadingHTTPServer(('127.0.0.1', int(os.getenv('PORT', '8000'))), Handler)
    server.bot = bot
    threading.Thread(target=poll, args=(bot,), daemon=True).start()
    print(f'Dashboard listening on port {server.server_port}', flush=True)
    server.serve_forever()
