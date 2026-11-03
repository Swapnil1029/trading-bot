import io
import json
import socket
import ssl
import unittest
import urllib.error
from unittest.mock import patch
from alpaca import Alpaca, AlpacaError


class ConnectionTests(unittest.TestCase):
    def setUp(self):
        with patch.dict('os.environ', {'APCA_API_KEY_ID': 'private-key', 'APCA_API_SECRET_KEY': 'private-secret'}):
            self.client = Alpaca()

    def check_failure(self, error, text, data=False):
        with patch('urllib.request.urlopen', side_effect=error):
            with self.assertRaises(AlpacaError) as context:
                self.client.request('/v2/account', data=data)
        message = str(context.exception)
        self.assertIn(text, message)
        self.assertNotIn('private-key', message)
        self.assertNotIn('private-secret', message)
        return message

    def test_mac_certificate_failure(self):
        self.check_failure(urllib.error.URLError(ssl.SSLCertVerificationError(1, 'certificate verify failed')), 'Install Certificates.command')

    def test_dns_and_timeout(self):
        self.check_failure(urllib.error.URLError(socket.gaierror(-2, 'failed')), 'DNS lookup failed')
        self.check_failure(TimeoutError(), 'timed out')

    def test_proxy_tunnel(self):
        self.check_failure(urllib.error.URLError(OSError('Tunnel connection failed: 403 Forbidden')), 'Proxy tunnel failed')

    def test_http_status_and_service(self):
        err = urllib.error.HTTPError('https://data.alpaca.markets', 401, 'Unauthorized', {}, io.BytesIO(b'private-secret'))
        self.check_failure(err, 'market data HTTP 401', data=True)

    def test_whitespace_normalized(self):
        with patch.dict('os.environ', {'APCA_API_KEY_ID':' key\n', 'APCA_API_SECRET_KEY':' secret '}):
            client = Alpaca()
        self.assertEqual(client.key, 'key')
        self.assertEqual(client.secret, 'secret')

    def test_internal_whitespace_rejected_without_request(self):
        self.client.key='private key'
        with patch('urllib.request.urlopen') as request:
            with self.assertRaisesRegex(AlpacaError, 'whitespace'):
                self.client.request('/v2/account')
            request.assert_not_called()

    def test_invalid_json_response(self):
        with patch('urllib.request.urlopen') as request:
            request.return_value.__enter__.return_value = io.BytesIO(b'<html>proxy error</html>')
            with self.assertRaisesRegex(AlpacaError, 'invalid response'):
                self.client.request('/v2/account')

if __name__ == '__main__': unittest.main()
