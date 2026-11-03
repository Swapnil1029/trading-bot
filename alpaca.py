"""Alpaca paper-only REST adapter. Uses the standard library and inherited TLS trust."""
import json
import os
import socket
import ssl
import urllib.error
import urllib.parse
import urllib.request


class AlpacaError(Exception):
    pass


class Alpaca:
    TRADING = 'https://paper-api.alpaca.markets'
    DATA = 'https://data.alpaca.markets'

    def __init__(self):
        self.key = os.getenv('APCA_API_KEY_ID', '').strip()
        self.secret = os.getenv('APCA_API_SECRET_KEY', '').strip()

    def request(self, path, method='GET', body=None, data=False):
        if not self.key or not self.secret:
            raise AlpacaError('Set APCA_API_KEY_ID and APCA_API_SECRET_KEY to your Alpaca paper credentials, then restart.')
        if any(c.isspace() for c in self.key + self.secret):
            raise AlpacaError('Alpaca credentials contain whitespace. Copy the paper key and secret again, then restart.')
        service = 'market data' if data else 'paper trading'
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
            if exc.code == 429:
                hint = 'Rate limit reached. Stop other bot instances and wait before retrying.'
            raise AlpacaError(f'Alpaca {service} HTTP {exc.code}. {hint}') from None
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            reason = exc.reason if isinstance(exc, urllib.error.URLError) else exc
            if isinstance(reason, ssl.SSLCertVerificationError):
                hint = ('TLS certificate verification failed. On macOS with python.org Python, run '
                        'Install Certificates.command in Applications > Python 3.x, then restart. '
                        'For managed networks, install the approved CA trust; do not disable TLS verification.')
            elif isinstance(reason, socket.gaierror):
                hint = 'DNS lookup failed. Check Internet access, DNS, and any configured proxy or VPN.'
            elif isinstance(reason, (TimeoutError, socket.timeout)):
                hint = 'Request timed out. Check Internet access, proxy/VPN settings, or Alpaca service status.'
            elif isinstance(reason, ConnectionRefusedError):
                hint = 'Connection refused. Check your firewall and any configured proxy or VPN.'
            elif 'Tunnel connection failed' in str(reason):
                hint = 'Proxy tunnel failed. Check the proxy allowlist for paper-api.alpaca.markets and data.alpaca.markets.'
            else:
                hint = 'Network connection failed. Check Internet access, proxy/VPN settings, or Alpaca service status.'
            raise AlpacaError(f'Alpaca {service}: {hint}') from None
        except (ValueError, UnicodeError):
            raise AlpacaError(f'Alpaca {service} returned an invalid response. Check service availability and proxy settings.') from None

    def latest(self, symbol):
        return self.request('/v2/stocks/' + urllib.parse.quote(symbol, safe='') + '/trades/latest?feed=iex', data=True)
