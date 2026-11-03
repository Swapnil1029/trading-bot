"""Alpaca paper-only REST adapter. Uses the standard library and inherited TLS trust."""
import json
import os
import urllib.error
import urllib.parse
import urllib.request


class AlpacaError(Exception):
    pass


class Alpaca:
    TRADING = 'https://paper-api.alpaca.markets'
    DATA = 'https://data.alpaca.markets'

    def __init__(self):
        self.key = os.getenv('APCA_API_KEY_ID', '')
        self.secret = os.getenv('APCA_API_SECRET_KEY', '')

    def request(self, path, method='GET', body=None, data=False):
        if not self.key or not self.secret:
            raise AlpacaError('Set APCA_API_KEY_ID and APCA_API_SECRET_KEY to your Alpaca paper credentials, then restart.')
        req = urllib.request.Request(
            (self.DATA if data else self.TRADING) + path,
            data=json.dumps(body).encode() if body is not None else None,
            method=method,
            headers={'APCA-API-KEY-ID': self.key, 'APCA-API-SECRET-KEY': self.secret,
                     'Content-Type': 'application/json', 'User-Agent': 'MeridianPaperBot/2.0'})
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            # Never include response bodies or request headers: keep credentials private.
            if exc.code == 404:
                return None
            hint = {401: 'Check your paper API credentials.', 403: 'Check API permissions, market-data subscription, and network policy.',
                    422: 'Alpaca rejected the order or parameters; inspect the paper account.'}.get(exc.code, 'Check Alpaca service availability.')
            raise AlpacaError(f'Alpaca HTTP {exc.code}. {hint}') from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise AlpacaError('Alpaca connection failed. Check Internet access and retry; order status is reconciled before further orders.') from None

    def latest(self, symbol):
        return self.request('/v2/stocks/' + urllib.parse.quote(symbol, safe='') + '/trades/latest?feed=iex', data=True)
