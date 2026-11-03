"""Read-only Alpaca diagnostics. Never sends orders or prints credentials."""
import os
import sys
from alpaca import Alpaca, AlpacaError


def main():
    client = Alpaca()
    print('Python:', sys.version.split()[0])
    print('Paper key:', 'set' if client.key else 'missing')
    print('Paper secret:', 'set' if client.secret else 'missing')
    for name in ('HTTPS_PROXY', 'HTTP_PROXY', 'SSL_CERT_FILE', 'SSL_CERT_DIR'):
        print(name + ':', 'set' if os.getenv(name) else 'not set')
    checks = [
        ('Paper account', lambda: client.request('/v2/account')),
        ('Market clock', lambda: client.request('/v2/clock')),
        ('SPY IEX data', lambda: client.latest('SPY')),
    ]
    failed = False
    for label, check in checks:
        try:
            response = check()
            if not response:
                raise AlpacaError('Endpoint returned no data.')
            print(label + ': OK')
        except AlpacaError as exc:
            failed = True
            print(label + ': FAIL — ' + str(exc))
        except Exception:
            failed = True
            print(label + ': FAIL — Unexpected response; check the installed app version.')
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
