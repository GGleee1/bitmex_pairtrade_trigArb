#CLI: python -m unittest test.test_bot
import sys
sys.path.append('C:/Users/User/Crypto_PerpFut_Arb/src') #specify the absolute path of bot module here
sys.path.append('C:/Users/User/Crypto_PerpFut_Arb/test') #specify the absolute path of test_utils module here

import unittest
from unittest.mock import Mock
#from unittest.mock import patch
import json
from datetime import datetime, timedelta
import copy
from collections import deque
from src import bot
import testing_utils as tu

with open('test/test_cfg/test_cfg.json', 'r') as f:
        cfg = json.load(f)

#Select which tests to skip or run
#trade and trade validation is tested separately
skip_test = {
    "init": True,
    "bootstrap_ref_prices": True,
    "update_impact_prices": True,
    "get_ref_signal": True,
    "is_triggered_open": True,
    "is_triggered_stoploss": False,
    "is_triggered_takeprofit": True
}
skip_reason = "As specified in skip_test"

class TestBot(unittest.TestCase):
    def setUp(self):
        self.cfg = dict(cfg) #copy.deepcopy(cfg)
        self.mock_OM = Mock()

    def tearDown(self):
        del self.cfg 
        del self.mock_OM
    
    @unittest.skipIf(skip_test["init"], skip_reason)  
    def test_innit_bad_last_update_1(self):
        """
        test that processor.__innit__ handles bad last_update value: not datetime strings.  
        """
        self.cfg["last_update"] = 101
        with self.assertRaisesRegex(TypeError, r'.*None or string of datetime'):
            proc = bot.processor(self.cfg, self.mock_OM)
    
    @unittest.skipIf(skip_test["init"], skip_reason)
    def test_innit_bad_last_update_2(self):
        """
        test that processor.__innit__ handles bad last_update value: datetime strings with wrong format.  
        """
        self.cfg["last_update"] = "1 Mar 2025"
        with self.assertRaisesRegex(ValueError, r'.*match timestamp_format'):
            proc = bot.processor(self.cfg, self.mock_OM)
    
    @unittest.skipIf(skip_test["bootstrap_ref_prices"], skip_reason)
    def test_bootstrap_ref_prices_full_1(self):
        """
        test that processor._bootstrap_ref_prices is called when last_update is None
        """
        self.cfg["last_update"] = None
        proc = bot.processor(self.cfg, self.mock_OM)

        now = datetime.now()+timedelta(hours=-8) #8hours adjustment of datetime.now() from your tz to BitMex tz    
        ts = datetime.strptime(self.cfg["last_update"], self.cfg["timestamp_format"])

        #set threshold here: last_update should be within X units of datetime.now()
        #note threshold should account for runtime of bootstrap_ref_prices increasing 60s each time a KeyError occurs. 
        self.assertTrue(now-timedelta(minutes=7)<=ts and ts<= now)
    
    @unittest.skipIf(skip_test["bootstrap_ref_prices"], skip_reason)
    def test_bootstrap_ref_prices_full_2(self):
        """
        test that processor._bootstrap_ref_prices fully replaces ref prices when last_update ts is outside current window
        """
        #stage initial self.cfg data
        #test assumes time of test is past 2025-03-11
        fm = self.cfg["timestamp_format"]

        start_ts = datetime.strptime("2025-03-10T00:00:00.000000Z", self.cfg["timestamp_format"])
        end_ts = datetime.strptime("2025-03-10T03:00:00.000000Z", self.cfg["timestamp_format"])
        
        self.cfg["ref_prices"]["A"] = tu.get_test_data(symbol=self.cfg["A"], startTime=start_ts, endTime=end_ts, ts_format=fm, interval="5m")
        self.cfg["ref_prices"]["B"] = tu.get_test_data(symbol=self.cfg["B"], startTime=start_ts, endTime=end_ts, ts_format=fm, interval="5m")
        self.cfg["last_update"] = self.cfg["ref_prices"]["A"][-1]["timestamp"]
        
        #save initial self.cfg data
        copyA = tu.dict_to_set(copy.deepcopy(self.cfg["ref_prices"]["A"]))
        copyB = tu.dict_to_set(copy.deepcopy(self.cfg["ref_prices"]["B"]))

        proc = bot.processor(self.cfg, self.mock_OM) 
        
        #conditions for successful test
        #set threshold here: last_update should be within X units of window
        #X units should be a slightly higher value than cfg['interval']
        r = self.cfg["ref_prices"]["A"]
        w = self.cfg["window_size"]
        time_diff = datetime.strptime(r[-1]["timestamp"], fm) - datetime.strptime(r[0]["timestamp"], fm) #length of time contained in ref_prices
        print(f"test_bootstrap_ref_prices_full_2 using window_size {w} days, processed and included ref_prices of length: {time_diff}")
        cond = (
            not len(copyA.intersection(tu.dict_to_set(self.cfg["ref_prices"]["A"]))) and
            not len(copyB.intersection(tu.dict_to_set(self.cfg["ref_prices"]["B"]))) 
        )
        self.assertTrue(cond)
    
    @unittest.skipIf(skip_test["bootstrap_ref_prices"], skip_reason)
    def test_bootstrap_ref_prices_partial(self):
        """
        test that processor._bootstrap_ref_prices partially replaces ref prices when last_update is is inside current window
        """
        #stage initial self.cfg data
        w = self.cfg["window_size"]
        fm = self.cfg["timestamp_format"]

        start_ts = datetime.now()+timedelta(hours=-8, days= -w * 1.2) #-8 hours is adjustment to bitmex timezone
        end_ts = datetime.now()+timedelta(hours=-8, days=-w * 0.5)
        
        self.cfg["ref_prices"]["A"] = tu.get_test_data(symbol=self.cfg["A"], startTime= start_ts, endTime= end_ts, interval="5m", ts_format=fm, marker="orig")
        self.cfg["ref_prices"]["B"] = tu.get_test_data(symbol=self.cfg["B"], startTime= start_ts, endTime= end_ts, interval="5m", ts_format=fm, marker="orig")
        self.cfg["last_update"] = self.cfg["ref_prices"]["A"][-1]["timestamp"]

        #save initial self.cfg data
        copyA = tu.dict_to_set(copy.deepcopy(self.cfg["ref_prices"]["A"]))
        copyB = tu.dict_to_set(copy.deepcopy(self.cfg["ref_prices"]["B"]))

        proc = bot.processor(self.cfg, self.mock_OM) 

        #conditions for successful test
        #set threshold here: last_update should be within X units of window
        #X units should be a slightly higher value than cfg['interval']
        r = self.cfg["ref_prices"]["A"]
        time_diff = datetime.strptime(r[-1]["timestamp"], fm) - datetime.strptime(r[0]["timestamp"], fm) #length of time contained in ref_prices
        
        print(f"test_bootstrap_ref_prices_partial using window_size {w} days, processed and included ref_prices of length: {time_diff}")
        print("test_bootstrap_ref_prices_partial ref_prices start data: {},\n end data: {}".format(r[0],r[-1]))
        cond = (
            len(copyA.intersection(tu.dict_to_set(self.cfg["ref_prices"]["A"]))) and
            len(copyB.intersection(tu.dict_to_set(self.cfg["ref_prices"]["B"])))
        )
        self.assertTrue(cond)   
    
    @unittest.skipIf(skip_test["update_impact_prices"], skip_reason)
    def test_update_impact_prices_bad_symbol(self):
        """
        test that processor.update_impact_prices handles wrong symbol in orderBookL2_25
        """
        with open('test/test_msg/msg_bad_symbol.json', 'r') as f:
            msg = json.load(f)['orderBookL2_25']
        proc = bot.processor(self.cfg, self.mock_OM)
        with self.assertRaisesRegex(Exception, r'.*does not match A or B.*' ):
            proc.update_impact_prices(msg)
    
    @unittest.skipIf(skip_test["update_impact_prices"], skip_reason)
    def test_update_impact_prices_lack_orders_1(self):
        """
        test that processor.update_impact_prices handles empty message
        """
        with open('test/test_msg/msg_empty.json', 'r') as f:
            msg = json.load(f)['orderBookL2_25']
            print(len(msg))
        proc = bot.processor(self.cfg, self.mock_OM)
        with self.assertRaisesRegex(Exception, r'.*only has one or no order.*' ):
            proc.update_impact_prices(msg)
        pass    
    
    @unittest.skipIf(skip_test["update_impact_prices"], skip_reason)
    def test_update_impact_prices_lack_orders_2(self):
        """
        test that processor.update_impact_prices handles message with only sell orders
        """
        with open('test/test_msg/msg_only_sell.json', 'r') as f:
            msg = json.load(f)['orderBookL2_25']
        proc = bot.processor(self.cfg, self.mock_OM)
        with self.assertRaisesRegex(Exception, r'.*only has either buy or sell orders.*' ):
            proc.update_impact_prices(msg)
        pass
    
    @unittest.skipIf(skip_test["update_impact_prices"], skip_reason)
    def test_update_impact_prices_lack_orders_3(self):
        """
        test that processor.update_impact_prices handles message with only buy orders
        """
        with open('test/test_msg/msg_only_buy.json', 'r') as f:
            msg = json.load(f)['orderBookL2_25']
        proc = bot.processor(self.cfg, self.mock_OM)
        with self.assertRaisesRegex(Exception, r'.*only has either buy or sell orders.*' ):
            proc.update_impact_prices(msg)
        pass
    
    @unittest.skipIf(skip_test["update_impact_prices"], skip_reason)
    def test_update_impact_prices_liquid(self):
        """
        test that processor.update_impact_prices calculates and updates impact prices correctly
        """
        with open('test/test_msg/msg_liquid.json', 'r') as f:
            msg = json.load(f)['orderBookL2_25']
        proc = bot.processor(self.cfg, self.mock_OM)
        proc.update_impact_prices(msg)

        #conditions for successful test
        cond = (
            round(self.cfg["tick_impact_px"]["A"]["askPrice"], 2) == 4988.24 and
            round(self.cfg["tick_impact_px"]["A"]["bidPrice"], 2) == 3189.53 and
            self.cfg["tick_impact_px"]["A"]["notional_sz"] == self.cfg["notional"]
        )
        self.assertTrue(cond)
    
    @unittest.skipIf(skip_test["update_impact_prices"], skip_reason)
    def test_update_impact_prices_less_liquid(self):
        """
        test that processor.update_impact_prices adjusts notional used when book lacks depth to support original notional, then calculates and updates impact prices correctly
        """
        with open('test/test_msg/msg_less_liquid.json', 'r') as f:
            msg = json.load(f)['orderBookL2_25']
        proc = bot.processor(self.cfg, self.mock_OM)
        proc.update_impact_prices(msg)

        #conditions for successful test
        cond = (
            round(self.cfg["tick_impact_px"]["A"]["askPrice"], 2) == 4940.30 and
            round(self.cfg["tick_impact_px"]["A"]["bidPrice"], 2) == 3193.25 and
            self.cfg["tick_impact_px"]["A"]["notional_sz"] == 400
        )
        self.assertTrue(cond)
    
    @unittest.skipIf(skip_test["get_ref_signal"], skip_reason)
    def test_get_ref_signal_single(self):
        """
        test that processor._get_ref_signal calculates a signal correctly
        """
        proc = bot.processor(self.cfg, self.mock_OM)
        pricesA = [{"askPrice":3193.25, "bidPrice":3188.55}]
        pricesB = [{"askPrice":4934.3, "bidPrice":4786.5}]
        shortSig, longSig = proc._get_ref_signal(pricesA, pricesB)
        cond = (
            round(shortSig[0], 6) == 0.646201 and
            round(longSig[0], 6) == 0.667137
        )
        self.assertTrue(cond)
    
    @unittest.skipIf(skip_test["get_ref_signal"], skip_reason)
    def test_get_ref_signal_multiple(self):
        """
        test that processor._get_ref_signal calculates signals correctly
        """
        proc = bot.processor(self.cfg, self.mock_OM)
        pricesA = [{"askPrice":3193.25, "bidPrice":3188.55},{"askPrice":3183.25, "bidPrice":3176.55}]
        pricesB = [{"askPrice":4934.3, "bidPrice":4786.5},{"askPrice":4914.3, "bidPrice":4786.5}]
        shortSig, longSig = proc._get_ref_signal(pricesA, pricesB)
        print(shortSig, longSig)
        cond = (
            list(map(lambda x: round(x,6), shortSig)) == [0.646201, 0.646389] and
            list(map(lambda x: round(x,6), longSig)) == [0.667137, 0.665048] 
        )
        self.assertTrue(cond)

#mock trade_pair, close_pair, and validation decorators 
    @unittest.skipIf(skip_test["is_triggered_open"], skip_reason)
    def test_is_triggered_openLong(self):
        """
        test that processor.is_triggered opens a long position on a valid long signal, and updates historical values in cfg
        """
        proc = bot.processor(self.cfg, self.mock_OM)
        proc.trade_pair= Mock()
        proc._validate_trade = Mock()

        #stage required cfg fields
        
        #round signal values to 6dp and convert ref_prices and ref_signals data to deque
        with open('test/test_cfg/test_cfg_openLong.json', 'r') as f:
            cfg = dict(json.load(f))
            proc.cfg = tu.format_deque(cfg)

        proc.A_fresh.set()
        proc.B_fresh.set()
        proc.is_triggered()
        
        #shortSig: 0.646201, longSig: 0.667137
        expected_position = {
            "state": "long",
            "signal": 0.6671367387443853,
            "entry_px": {
                "A": 3193.25,
                "B": 4786.5
            }
        }

        expected_ref_signals = {
            "short":{
                "data":deque([0, 0.6462010822203758]),
                "mean": 0.3231005411101879,
                "std": 0.45693316724811345
            },
            "long":{
                "data":deque([0.63, 0.6671367387443853]),
                "mean": 0.6485683693721926,
                "std": 0.026259639797308023
            }
        }

        with self.subTest():
            self.assertDictEqual(proc.cfg["position"], expected_position)
        with self.subTest():
            self.assertDictEqual(proc.cfg["ref_signals"], expected_ref_signals)     
    
    @unittest.skipIf(skip_test["is_triggered_open"], skip_reason)
    def test_is_triggered_openShort(self):
        """
        test that processor.is_triggered opens a short position on a valid short signal, and updates historical values in cfg
        """
        proc = bot.processor(self.cfg, self.mock_OM)
        proc.trade_pair= Mock()
        proc._validate_trade = Mock()
        
        #stage required cfg fields
        
        #round signal values to 6dp and convert ref_prices and ref_signals data to deque
        with open('test/test_cfg/test_cfg_openShort.json', 'r') as f:
            cfg = dict(json.load(f))
            proc.cfg = tu.format_deque(cfg)

        proc.A_fresh.set()
        proc.B_fresh.set()
        proc.is_triggered()
        
        #shortSig: 0.646201, longSig: 0.667137
        expected_position = {
            "state": "short",
            "signal": 0.6462010822203758,
            "entry_px": {
                "A": 3188.55,
                "B": 4934.3
            }
        }

        expected_ref_signals = {
            "short":{
                "data":deque([0.51, 0.6462010822203758]),
                "mean": 0.5781005411101878,
                "std": 0.0963087088429742
            },
            "long":{
                "data":deque([0, 0.6671367387443853]),
                "mean": 0.33356836937219264,
                "std": 0.47173691194483297
            }
        }
         
        with self.subTest():
            self.assertDictEqual(proc.cfg["position"], expected_position)
        with self.subTest():
            self.assertDictEqual(proc.cfg["ref_signals"], expected_ref_signals)
   
    @unittest.skipIf(skip_test["is_triggered_stoploss"], skip_reason)
    def test_is_triggered_ShortSL(self):
        """
        test that processor.is_triggered closes short position on a valid stoploss signal, and updates historical values in cfg
        """
        proc = bot.processor(self.cfg, self.mock_OM)
        proc.close_pair = Mock()
        proc._validate_trade_close = Mock()
        #stage required cfg fields
        
        #round signal values to 6dp and convert ref_prices and ref_signals data to deque
        with open('test/test_cfg/test_cfg_stopLossShort.json', 'r') as f:
            cfg = dict(json.load(f))
            proc.cfg = tu.format_deque(cfg)

        proc.A_fresh.set()
        proc.B_fresh.set()
        proc.is_triggered()

        expected_position = {
            "state": None,
            "signal": None,
            "entry_px":{"A": None, "B":None}
        }

        expected_ref_signals = {
            "short":{
                "data":deque([0, 1]),
                "mean": 0.50,
                "std": 0.7071067811865476
            },
            "long":{
                "data":deque([0, 1]),
                "mean": 0.5,
                "std": 0.7071067811865476
            }
        }
         
        with self.subTest():
            self.assertDictEqual(proc.cfg["position"], expected_position)
        with self.subTest():
            self.assertDictEqual(proc.cfg["ref_signals"], expected_ref_signals)
    
    @unittest.skipIf(skip_test["is_triggered_takeprofit"], skip_reason)
    def test_is_triggered_ShortTP(self):
        """
        test that processor.is_triggered closes a short position on a valid take profit signal, and updates historical values in cfg
        """
        proc = bot.processor(self.cfg, self.mock_OM)
        proc.close_pair = Mock()
        proc._validate_trade_close = Mock()

        #stage required cfg fields
        
        #round signal values to 6dp and convert ref_prices and ref_signals data to deque
        with open('test/test_cfg/test_cfg_takeProfShort.json', 'r') as f:
            cfg = dict(json.load(f))
            proc.cfg = tu.format_deque(cfg)

        proc.A_fresh.set()
        proc.B_fresh.set()
        proc.is_triggered()

        expected_position = {
            "state": None,
            "signal": None,
            "entry_px":{"A": None, "B":None}
        }

        expected_ref_signals = {
            "short":{
                "data":deque([0, 1]),
                "mean": 0.50,
                "std": 0.7071067811865476
            },
            "long":{
                "data":deque([0, 1]),
                "mean": 0.5,
                "std": 0.7071067811865476
            }
        }
         
        with self.subTest():
            self.assertDictEqual(proc.cfg["position"], expected_position)
        with self.subTest():
            self.assertDictEqual(proc.cfg["ref_signals"], expected_ref_signals)
    
    @unittest.skipIf(skip_test["is_triggered_stoploss"], skip_reason)
    def test_is_triggered_LongSL(self):
        """
        test that processor.is_triggered closes a long position on a valid stoploss signal, and updates historical values in cfg
        """
        proc = bot.processor(self.cfg, self.mock_OM)
        proc.close_pair = Mock()
        proc._validate_trade_close = Mock()

        #stage required cfg fields
        
        #round signal values to 6dp and convert ref_prices and ref_signals data to deque
        with open('test/test_cfg/test_cfg_stopLossLong.json', 'r') as f:
            cfg = dict(json.load(f))
            proc.cfg = tu.format_deque(cfg)
        print(proc.cfg["ref_signals"])
        proc.A_fresh.set()
        proc.B_fresh.set()
        proc.is_triggered()
        print(proc.cfg["ref_signals"])
        expected_position = {
            "state": None,
            "signal": None,
            "entry_px":{"A": None, "B":None}
        }

        expected_ref_signals = {
            "short":{
                "data":deque([0, 1]),
                "mean": 0.50,
                "std": 0.7071067811865476
            },
            "long":{
                "data":deque([0, 1]),
                "mean": 0.5,
                "std": 0.7071067811865476
            }
        }
         
        with self.subTest():
            self.assertDictEqual(proc.cfg["position"], expected_position)
        with self.subTest():
            self.assertDictEqual(proc.cfg["ref_signals"], expected_ref_signals)
    
    @unittest.skipIf(skip_test["is_triggered_takeprofit"], skip_reason)
    def test_is_triggered_LongTP(self):
        """
        test that processor.is_triggered closes a long position on a valid take profit signal, and updates historical values in cfg
        """
        proc = bot.processor(self.cfg, self.mock_OM)
        proc.close_pair = Mock()
        proc._validate_trade_close = Mock()

        #stage required cfg fields

        #round signal values to 6dp and convert ref_prices and ref_signals data to deque
        with open('test/test_cfg/test_cfg_takeProfShort.json', 'r') as f:    
            cfg = dict(json.load(f))
            proc.cfg = tu.format_deque(cfg)
        
        proc.A_fresh.set()
        proc.B_fresh.set()
        proc.is_triggered()
  
        expected_position = {
            "state": None,
            "signal": None,
            "entry_px":{"A": None, "B":None}
        }

        expected_ref_signals = {
            "short":{
                "data":deque([0, 1]),
                "mean": 0.50,
                "std": 0.7071067811865476
            },
            "long":{
                "data":deque([0, 1]),
                "mean": 0.5,
                "std": 0.7071067811865476
            }
        }
         
        with self.subTest():
            self.assertDictEqual(proc.cfg["position"], expected_position)
        with self.subTest():
            self.assertDictEqual(proc.cfg["ref_signals"], expected_ref_signals)    