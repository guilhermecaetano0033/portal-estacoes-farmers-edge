"""Regressao: Session.get nao pode duplicar allow_redirects."""
import unittest
from unittest.mock import patch
from requests import Response, Session
from atualizar import FarmTokenSession

class TokenSessionTests(unittest.TestCase):
    def test_get_adds_token_without_duplicate_redirect_option(self):
        response = Response()
        response.status_code = 200
        with patch.object(Session, 'request', return_value=response) as base_request:
            s = FarmTokenSession('TEST_TOKEN')
            self.assertIs(s.get('https://admin.farmcommand.com/weather/81263/historical-summary-hourly/', params={'startDate':'2026-09-01'}, timeout=10), response)
            self.assertEqual(base_request.call_args.kwargs['params']['token'], 'TEST_TOKEN')
            self.assertFalse(base_request.call_args.kwargs['allow_redirects'])
            self.assertEqual(base_request.call_args.kwargs['params']['startDate'], '2026-09-01')

    def test_rejects_other_hosts(self):
        with self.assertRaises(RuntimeError):
            FarmTokenSession('TEST_TOKEN').get('https://example.com/')

if __name__ == '__main__':
    unittest.main()
