import unittest
from server import Bot

class StrategyTests(unittest.TestCase):
    def bot(self):
        bot = Bot(persist=False)
        bot.short, bot.long = 2, 3
        return bot

    def test_crossover_and_accounting(self):
        b = self.bot()
        for i, price in enumerate([3, 2, 1, 4, 5]):
            b.tick(price, 100+i*10)
        self.assertEqual(len(b.trades), 1)
        self.assertEqual(b.trades[0]['side'], 'BUY')
        self.assertEqual(b.cash, 7500)
        self.assertAlmostEqual(b.qty, 2497.5/4)
        for i, price in enumerate([1, 1]):
            b.tick(price, 150+i*10)
        self.assertEqual(len(b.trades), 2)
        self.assertEqual(b.trades[0]['side'], 'SELL')
        self.assertEqual(b.qty, 0)
        self.assertAlmostEqual(b.snapshot()['pnl'], b.realized)
        self.assertLess(b.realized, 0)

    def test_pause_monitors_without_orders(self):
        b = self.bot()
        b.configure({'running': False})
        for i, p in enumerate([3,2,1,4,5,1]): b.tick(p,100+i*10)
        self.assertEqual(len(b.trades), 0)
        self.assertTrue(any(e['kind']=='SIGNAL' for e in b.events))

    def test_gap_rewarms(self):
        b = self.bot()
        for i,p in enumerate([3,2,1]): b.tick(p,100+i*10)
        b.tick(10,200)
        self.assertEqual(len(b.prices),1)
        self.assertIsNone(b.regime)
        self.assertEqual(len(b.trades),0)

    def test_invalid_settings(self):
        for config in ({'short':20,'long':5},{'short':2.5},{'long':121},{'running':'false'}):
            with self.assertRaises(ValueError): self.bot().configure(config)

    def test_no_initial_order_or_duplicate_position(self):
        b=self.bot()
        for i,p in enumerate([1,2,3,4,5]): b.tick(p,100+i*10)
        self.assertEqual(len(b.trades),0)
        b.execute('BUY',5,160)
        b.execute('BUY',6,170)
        self.assertEqual(len(b.trades),1)

if __name__=='__main__': unittest.main()
