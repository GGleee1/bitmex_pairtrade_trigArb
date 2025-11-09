#CLI: python -m unittest test.test_bot_trade
import sys
sys.path.append('C:/Users/User/BitMex/pairTrade/twoPortfolios/src') #specify the absolute path of bot module here
from src import my_order_mgr
from src.credentials import APIKEY, APISECRET
import test.test_bot_trade_values as tv
import unittest, threading, copy


skip_test={
    "test_noValidate_long": False,
    "test_noValidate_short": False,
    "test_validate_open_pass": False,
    "test_validate_open_fail": False,
    "test_validate_close_pass": False,
    "test_validate_close_fail": False
}
skip_reason = "As specified in skip_test"

class ResponsiveThread(threading.Thread): #Thread that returns value on .join()
    def __init__(self, group=None, target=None, name=None, args=(), kwargs={}, verbose=None):
        # Initializing the Thread class
        super().__init__(group, target, name, args, kwargs)
        self._return = None

    # Overriding the Thread.run function
    def run(self):
        if self._target is not None:
            self._return = self._target(*self._args, **self._kwargs)

    def join(self):
        super().join()
        return self._return

#quick and dirty way to trade funcs w/ and w/o validation wrappers
#Define trade funcs separately, and wrap when necessary
class mock_bot:
    def __init__(self, cfg, OM):
        self.cfg = cfg
        self.OM = OM
    #wrapper to validate trade
    def _validate_trade(fn):
        def cancel_or_close(self, res):
            for r in res:
                if r is None: continue
                if r[0]["ordStatus"] == "New": #cancel open orders
                    thread = threading.Thread(target = self.OM.cancel, args=(r[0]["orderID"]))
                    thread.start()
                    thread.join()
                    #self.OM.cancel(r[0]["orderID"])

                elif r[0]["ordStatus"]== "Filled": #close filled orders
                    closeSide = "Buy" if r[0]["side"] == "Sell" else "Sell"
                    thread = threading.Thread(target = self.OM.close, args=(closeSide, r[0]["symbol"]))
                    thread.start()
                    thread.join()
                    #self.OM.close(
                    #    side = closeSide,
                    #    symbol = r[0]["symbol"]
                    #)
                else: 
                    pass #rejected or canceled orders not actionable

        def wrapped(*args, **kwargs):
            self_arg = args[0]
            res = fn(*args, **kwargs)

            if any((r is None) for r in res): #one or both orders failed to send
                cancel_or_close(self_arg, res)
                #botu.noti(self_arg.webhook, "Some orders in trade_pair failed to send.\nCancelling orders and closing any unpaired positions.")
                return False
            else:                
                if all(r[1]==200 for r in res) and all(r[0]["ordStatus"] == "Filled" for r in res): #both orders sent and filled
                    #botu.noti(self_arg.webhook, "All orders in trade_pair sent and filled.")
                    return True
                else: 
                    #botu.noti(self_arg.webhook, "Unhandled exception caught in trade_pair.\nManual order & position handling required.")
                    return False       
        return wrapped

    #wrapper to validate close trade. Will not cancel unfilled orders, only retry and notify. 
    def _validate_trade_close(fn):
        #For retry, cannot reuse close_pair as its decorator can get called recursively = infinite notis.
        def resend_ord(self, t):
            state = self.cfg["position"]["state"]
            s = self.cfg["position"][t]["exitOrdBk_side_per_entry_state"][state]
            thread = threading.Thread(target=self.OM.close, args=(s,t))
            thread.start()
            thread.join()
            #self.OM.close(s, t, extra_attrs={})            
            pass
        
        def wrapped(*args, **kwargs):
            self_arg = args[0]
            res = fn(*args, **kwargs)

            if any((r is None) for r in res):
                #botu.noti(self_arg.webhook, "Some orders in close_pair unsent.\nAttempting to resend.\nManual order & position handling required.")    
                tickers = set(self_arg.cfg["ticker_list"])
                sent = set(r[0]["symbol"] for r in res if r is not None)
                unsent = tickers.difference(sent)
                for t in unsent:
                    resend_ord(self_arg, t)
                return False

            elif all(r[0]["ordStatus"] == "Filled" for r in res):
                #botu.noti(self_arg.webhook, "All orders in close_pair sent and filled.")
                return True
            
            elif all((r[0]["ordStatus"] == "Filled") or (r[0]["ordStatus"]=="New") for r in res):
                #botu.noti(self_arg.webhook, "All orders in close_pair sent, but some orders remain open.\nManual order & position handling required.")
                return False
            
            else:
                #botu.noti(self_arg.webhook, "Some orders sent, but status rejected, or cancelled.\nAttempting to resend.\nManual order & position handling required.")
                for r in res:
                    if r[0]["ordStatus"] != "New" and r[0]["ordStatus"]!="Filled":
                        resend_ord(self_arg, r[0]["symbol"])
                return False
        
        return wrapped

    def trade_pair_noValidate(self, direction):
        qty = lambda t, bid_ask: self.cfg["ticker_info"][t]["impact_px"]["notional_sz"][f"Cont_{bid_ask}"]
        if direction == "long":
            threads = [
                ResponsiveThread(target = self.OM.buy, args=("ETHZ25", qty("ETHZ25", "ask"), None), kwargs={"extra_attrs": {}}),
                ResponsiveThread(target = self.OM.sell, args=("ETHUSDZ25", qty("ETHUSDZ25", "bid"), None), kwargs={"extra_attrs": {}}),
                ResponsiveThread(target = self.OM.buy, args=("XBTZ25", qty("XBTZ25", "ask"), None), kwargs={"extra_attrs": {}})
                ]
        else: #direction == "short"
            threads = [
                ResponsiveThread(target = self.OM.sell, args=("ETHZ25", qty("ETHZ25", "bid"), None), kwargs={"extra_attrs": {}}),
                ResponsiveThread(target = self.OM.buy, args=("ETHUSDZ25", qty("ETHUSDZ25", "ask"), None), kwargs={"extra_attrs": {}}),
                ResponsiveThread(target = self.OM.sell, args=("XBTZ25", qty("XBTZ25", "bid"), None), kwargs={"extra_attrs": {}})
                ]
        
        for thread in threads:
            thread.start()
        
        responses =[]
        for thread in threads:
            responses.append(thread.join())

        threads.clear()
        return responses   
    
    def close_pair_noValidate(self):
        state = self.cfg["position"]["state"] #should only be long or short.
        threads = []
        for t in self.cfg["ticker_list"]:
            s = self.cfg["position"][t]["exitOrdBk_side_per_entry_state"][state]
            threads.append(
                ResponsiveThread(target = self.OM.close, args=(s, t), kwargs={"extra_attrs": {}}),
            )

        for thread in threads:
            thread.start()
        
        responses =[]
        for thread in threads:
            responses.append(thread.join())

        threads.clear()
        return responses
    
    @_validate_trade
    def trade_pair_validate(self, direction):
        return self.trade_pair_noValidate(direction)
    
    @_validate_trade_close
    def close_pair_validate(self):
        return self.close_pair_noValidate()

OM = my_order_mgr.OrderMgr(
    base_url = "https://testnet.bitmex.com/api/v1/",
    apiKey= APIKEY,
    apiSecret=APISECRET,
    postOnly=True
)

class TestBotTrade(unittest.TestCase):
    def setUp(self):
        cfg = copy.deepcopy(tv.CFG)
        self.bot = mock_bot(cfg, OM)
    
    def tearDown(self):
        del self.bot

    @unittest.skipIf(skip_test["test_noValidate_long"], reason = skip_reason)
    def test_noValidate_long(self):
        """test that bot correctly opens and closes long positions"""
        #open
        self.bot.trade_pair_noValidate("long")
        open_pos = OM.get_position_info(filter={"isOpen":"true"})[0]

        open_res = {}
        for p in open_pos:
            open_res.update({p["symbol"]:p["currentQty"]})

        #close
        self.bot.cfg["position"]["state"]="long"
        self.bot.close_pair_noValidate()
        open_pos = OM.get_position_info(filter={"isOpen":"true"})[0]
        
        self.assertTrue(
            open_res == tv.TRADE_NOVALIDATE_LONG and
            not open_pos) #no open positions after closing

    @unittest.skipIf(skip_test["test_noValidate_short"], reason = skip_reason)
    def test_noValidate_short(self):
        """test that bot correctly opens and closes short positions""" 
        #open
        self.bot.trade_pair_noValidate("short")
        open_pos = OM.get_position_info(filter={"isOpen":"true"})[0]

        open_res = {}
        for p in open_pos:
            open_res.update({p["symbol"]:p["currentQty"]})

        #close
        self.bot.cfg["position"]["state"]="short" 
        self.bot.close_pair_noValidate()
        open_pos = OM.get_position_info(filter={"isOpen":"true"})[0]
        
        self.assertTrue(
            open_res == tv.TRADE_NOVALIDATE_SHORT and
            not open_pos) #no open positions after closing

    @unittest.skipIf(skip_test["test_validate_open_pass"], reason = skip_reason)
    def test_validate_open_pass(self):
        """test that _validate_trade recognizes successful trade"""
        wrapped_res_true = self.bot.trade_pair_validate("long")
        open_pos = OM.get_position_info(filter={"isOpen":"true"})[0]

        open_res = {}
        for p in open_pos:
            open_res.update({p["symbol"]:p["currentQty"]})

        self.bot.cfg["position"]["state"]="long"
        self.bot.close_pair_noValidate()

        self.assertTrue(
            wrapped_res_true and
            open_res == tv.TRADE_NOVALIDATE_LONG
        )

    @unittest.skipIf(skip_test["test_validate_open_fail"], reason = skip_reason)
    def test_validate_open_fail(self):
        """test that _validate_trade recognizes failed trade"""
        
        #use bad lot size to trigger fail
        self.bot.cfg["ticker_info"]["ETHZ25"]["impact_px"]["notional_sz"]["Cont_ask"]=1
        wrapped_res_false = self.bot.trade_pair_validate("long")

        #check validator closed/cancelled all positions
        open_pos = OM.get_position_info(filter={"isOpen":"true"})[0]

        self.assertTrue(
            wrapped_res_false == False and
            not open_pos #no open positions after failing validation
        )        

    @unittest.skipIf(skip_test["test_validate_close_pass"], reason = skip_reason)
    def test_validate_close_pass(self):
        """test that _validate_trade recognizes successful trade"""
        
        self.bot.trade_pair_noValidate("long")
        self.bot.cfg["position"]["state"]="long"
        
        wrapped_res_true = self.bot.close_pair_validate()
        open_pos = OM.get_position_info(filter={"isOpen":"true"})[0]

        self.assertTrue(
            wrapped_res_true and
            not open_pos
        )

    @unittest.skipIf(skip_test["test_validate_close_fail"], reason = skip_reason)
    def test_validate_close_fail(self):
        """test that _validate_trade recognizes failed trade"""
        
        #specify wrong side on close to trigger fail
        self.bot.cfg["position"]["ETHZ25"]["exitOrdBk_side_per_entry_state"]["long"] = "Buy"
        self.bot.trade_pair_noValidate("long")
        self.bot.cfg["position"]["state"]="long"

        wrapped_res_false =  self.bot.close_pair_validate()

        #there will be an open ETHZ25 position, close that properly
        OM.close("Sell", "ETHZ25")
        
        self.assertTrue(wrapped_res_false == False)
    
    
    