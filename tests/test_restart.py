import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from server import StockBot


class RestartTests(unittest.TestCase):
    def test_restart_restores_enabled_and_paused_only_when_opted_in(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch('server.STOCK_DATA', Path(directory)/'state.json'), patch.dict('os.environ', {'ALPACA_SYMBOL':'SPY','RESUME_ON_RESTART':'true'}):
                bot=StockBot()
                self.assertFalse(bot.running)
                bot.configure({'running':True})
                self.assertTrue(StockBot().running)
                with patch.dict('os.environ', {'RESUME_ON_RESTART':'false'}):
                    self.assertFalse(StockBot().running)
                bot.configure({'running':False})
                self.assertFalse(StockBot().running)

    def test_pending_survives_restart_and_symbol_change_starts_paused(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch('server.STOCK_DATA', Path(directory)/'state.json'), patch.dict('os.environ', {'ALPACA_SYMBOL':'SPY','RESUME_ON_RESTART':'true'}):
                bot=StockBot()
                bot.running=True
                bot.pending='meridian-unresolved'
                bot.save()
                restarted=StockBot()
                self.assertEqual(restarted.pending,'meridian-unresolved')
                self.assertIsNone(restarted.regime)
                self.assertEqual(len(restarted.prices),0)
                with patch.dict('os.environ', {'ALPACA_SYMBOL':'AAPL'}):
                    changed=StockBot()
                    self.assertFalse(changed.running)
                    self.assertEqual(changed.pending,'meridian-unresolved')

if __name__=='__main__':unittest.main()
