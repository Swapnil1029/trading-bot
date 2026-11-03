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


def poll(bot):
    while True:
        try:
            request = urllib.request.Request('https://api.coinbase.com/v2/prices/BTC-USD/spot', headers={'User-Agent': 'MovingAveragePaperBot/1.0', 'Cache-Control': 'no-cache'})
            with urllib.request.urlopen(request, timeout=8) as response:
                price = float(json.load(response)['data']['amount'])
            if not 0 < price < float('inf'):
                raise ValueError('Invalid market price')
            bot.tick(price)
        except Exception as exc:
            with bot.lock:
                if bot.feed != 'Unavailable':
                    bot.event('FEED', 'Live feed unavailable. No paper orders will execute until fresh data returns.')
                bot.feed = 'Unavailable'
                bot.error = f'{type(exc).__name__}: live market request failed. Check network access to api.coinbase.com.'
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
    bot = Bot()
    bot.event('BOT', 'Dashboard connected. Paper trading only; no real orders.')
    server = ThreadingHTTPServer(('0.0.0.0', int(os.getenv('PORT', '8000'))), Handler)
    server.bot = bot
    threading.Thread(target=poll, args=(bot,), daemon=True).start()
    print(f'Dashboard listening on port {server.server_port}', flush=True)
    server.serve_forever()
