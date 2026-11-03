import time
import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from alpaca import Alpaca, AlpacaError
from server import StockBot


class FakeAlpaca:
    def __init__(self):
        self.posts=[]
        self.closed=False
        self.stale=False
        self.working=False
        self.uncertain=False
        self.resolved=None
        self.quantity='0'

    def request(self,path,method='GET',body=None,**kwargs):
        if method=='POST':
            self.posts.append(body)
            if self.uncertain: raise AlpacaError('Timeout')
            return dict(id='order-1',status='accepted')
        if path.startswith('/v2/orders:by_client_order_id'): return self.resolved
        if path=='/v2/account':return dict(cash='10000',equity='11000',last_equity='10900',buying_power='10000',status='ACTIVE')
        if path=='/v2/positions':
            return [] if self.quantity=='0' else [dict(symbol='SPY',qty=self.quantity,cost_basis='500',market_value='505')]
        if path.startswith('/v2/orders?status=open'):return [dict(symbol='SPY')] if self.working else []
        if path.startswith('/v2/orders?'):return []
        if path=='/v2/clock':return dict(is_open=not self.closed,next_open='2027-01-04T14:30:00Z')
        if path.startswith('/v2/assets/'):return {'tradable':True,'class':'us_equity'}
        raise AssertionError(path)

    def latest(self,symbol):
        stamp=datetime.fromtimestamp(time.time()-(100 if self.stale else 0),timezone.utc).isoformat()
        return dict(trade=dict(p=500,t=stamp))


class StockTests(unittest.TestCase):
    def setUp(self):
        self.api=FakeAlpaca()
        self.bot=StockBot(persist=False,client=self.api)

    def test_paper_endpoint_only_and_missing_credentials(self):
        with patch.dict('os.environ',{},clear=True):
            client=Alpaca()
            self.assertEqual(client.TRADING,'https://paper-api.alpaca.markets')
            with self.assertRaises(AlpacaError):client.request('/v2/account')

    def test_account_sync_and_paused_start(self):
        self.bot.refresh()
        self.assertFalse(self.bot.running)
        self.assertEqual(self.bot.snapshot()['equity'],11000)
        self.assertEqual(self.bot.snapshot()['pnl'],100)
        self.assertEqual(len(self.bot.prices),1)
        self.assertEqual(self.api.posts,[])

    def test_market_closed_and_stale_feed(self):
        self.api.closed=True
        self.bot.refresh()
        self.assertEqual(self.bot.feed,'Market closed')
        self.assertEqual(len(self.bot.prices),0)
        self.api.closed=False;self.api.stale=True
        with self.assertRaises(ValueError):self.bot.refresh()
        self.assertEqual(self.api.posts,[])

    def test_whole_share_buy_and_pending_suppression(self):
        self.bot.refresh()
        self.bot.execute('BUY',500,time.time())
        self.assertEqual(self.api.posts[0]['qty'],'4')
        self.assertEqual(self.api.posts[0]['time_in_force'],'day')
        self.assertEqual(self.api.posts[0]['symbol'],'SPY')
        self.bot.execute('BUY',500,time.time())
        self.assertEqual(len(self.api.posts),1)
        self.assertEqual(self.bot.cash,10000)  # only broker-confirmed balances

    def test_uncertain_submission_never_retried(self):
        self.bot.refresh();self.api.uncertain=True
        with self.assertRaises(AlpacaError):self.bot.execute('BUY',500,time.time())
        self.assertIsNotNone(self.bot.pending)
        with self.assertRaises(ValueError):self.bot.refresh()
        self.bot.execute('BUY',500,time.time())
        self.assertEqual(len(self.api.posts),1)
        self.api.resolved=dict(status='filled',client_order_id=self.bot.pending,filled_qty='4')
        self.bot.refresh()
        self.assertIsNone(self.bot.pending)

    def test_working_orders_and_no_short_sales(self):
        self.api.working=True;self.bot.refresh()
        self.bot.execute('BUY',500,time.time())
        self.assertEqual(self.api.posts,[])
        self.api.working=False;self.bot.refresh()
        self.bot.execute('SELL',500,time.time())
        self.assertEqual(self.api.posts,[])
        self.api.quantity='2';self.bot.refresh()
        self.bot.execute('SELL',500,time.time())
        self.assertEqual(self.api.posts[-1]['qty'],'2.0')

    def test_crossover_submits_to_alpaca(self):
        self.bot.refresh();self.bot.prices.clear();self.bot.last_tick=0
        self.bot.short,self.bot.long=2,3
        self.bot.configure({'running':True})
        for i,p in enumerate([3,2,1,4,5]):self.bot.tick(p,100+i*10)
        self.assertEqual(len(self.api.posts),1)
        self.assertEqual(self.api.posts[0]['side'],'buy')

if __name__=='__main__':unittest.main()
