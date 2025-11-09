#CLI: python -m unittest test.test_custom_calcs

from src.util import custom_calcs as cc
import test.test_custom_calcs_values as tv
from math import isclose
import unittest, sys


#sys.path.append('C:/Users/User/BitMex/pairTrade/twoPortfolios/src') #specify the absolute path of bot module here

skip_test = {
    "calc_ref_signal": False,
    "get_szInUSD": False,
    "get_PnLInUSD": False,
    "format_ordBook": False,
    "optimise_num_lots": False,
    "calc_impact_px": False,
    "calc_ticker_pnl": False,
    "calc_trade_pnl": False,
    "calc_min_notl": False,
    "det_notl_dir": False
}
skip_reason = "As specified in skip_test"

class TestCustomCalcs(unittest.TestCase):
    @unittest.skipIf(skip_test["calc_ref_signal"], skip_reason)
    def test_calc_ref_signal(self):
        assert cc.calc_ref_signal(tv.CALC_REF_SIGNAL) == tv.CALC_REF_SIGNAL_RES

    @unittest.skipIf(skip_test["get_szInUSD"], skip_reason)
    def test_getszInUSD(self):
        cfg = tv.GET_SZINUSD["CFG"]
        res = []
        for t in cfg["ticker_info"]:
            calc = cc.get_szInUSD(cfg, t)
            res.append(calc(2, 4691))
        assert res == tv.GET_SZINUSD_RES

    @unittest.skipIf(skip_test["get_PnLInUSD"], skip_reason)
    def test_getPnLInUSD(self):
        cfg = tv.GET_SZINUSD["CFG"] #reusing test values, no need for duplicates
        res = []
        for t in cfg["ticker_info"]:
            calc = cc.get_PnLInUSD(cfg, t)
            res.append(round(calc(-10, 5),2))
        assert res == tv.GET_PNLINUSD_RES
    
    @unittest.skipIf(skip_test["format_ordBook"], skip_reason)
    def test_format_ordBook(self):
        cfg = tv.GET_SZINUSD["CFG"] #reusing test values, no need for duplicates
        res =cc.format_ordBook(tv.FORMAT_ORDBOOK, cfg)
        assert res == tv.FORMAT_ORDBOOK_RES
    
    @unittest.skipIf(skip_test["optimise_num_lots"], skip_reason)
    def test_optimise_num_lots(self):
        #reusing test values, no need for duplicates
        cfg = tv.OPTIMISE_NUM_LOTS["CFG"]
        ordBkLevel = tv.FORMAT_ORDBOOK_RES[0]

        #case 1: actual - whole lots to fill <=0.5
        res1 = cc.optimise_num_lots(cfg, ordBkLevel, 44.75)

        #case 2: actual - whole lots to fill > 0.5
        res2 = cc.optimise_num_lots(cfg, ordBkLevel, 20)

        assert (res1 == 1000 and res2 == 0)

    @unittest.skipIf(skip_test["calc_impact_px"], skip_reason)
    def test_calc_impact_px(self):
        #reusing test values, no need for duplicates
        cfg = tv.OPTIMISE_NUM_LOTS["CFG"]
        ordBk_f = tv.FORMAT_ORDBOOK_RES
        
        #case 1: Buy
        res1 = cc.calc_impact_px(cfg, ordBk_f, 100, "Buy")

        #case 2: Sell
        res2 = cc.calc_impact_px(cfg, ordBk_f, 100, "Sell")       
        
        def check_res(res, exp):
            return all(isclose(i,j) for i,j in tuple(zip(res, exp)))

        exp_res = tv.CALC_IMPACT_PX_RES
        
        assert(
            check_res(res1, exp_res["case1"]) and
            check_res(res2, exp_res["case2"])
        )
    
    @unittest.skipIf(skip_test["calc_ticker_pnl"], skip_reason)
    def test_calc_ticker_pnl(self):
        cfg = tv.CALC_TICKER_PNL["CFG"]
        ticker = "ETHZ25" #This is based on ticker in cfg["position"]
        ExitOB_t = tv.FORMAT_ORDBOOK_RES #reusing test values, no need for duplicates
        
        #case 1: close long position
        cfg["position"]["state"] = "long"
        res1 = cc.calc_ticker_pnl(cfg, ticker, ExitOB_t)

        #case 2: close short position
        cfg["position"]["state"] = "short"
        res2 = cc.calc_ticker_pnl(cfg, ticker, ExitOB_t)

        #case 3: Orderbk insufficient liquidity to close entire pos
        #TODO Unhandled case. Implementation required.
        
        exp_res = tv.CALC_TICKER_PNL_RES

        assert(
            isclose(res1, exp_res["case1"]) and
            isclose(res2, exp_res["case2"])
        )

    @unittest.skipIf(skip_test["calc_trade_pnl"], skip_reason)
    def test_calc_trade_pnl(self):
        cfg = tv.CALC_TRADE_PNL["CFG"]
        ExitOB = {}
        for t in cfg["ticker_list"]:
            ExitOB.update({t: tv.FORMAT_ORDBOOK_RES}) #Mock orderbook per ticker
        
        res = cc.calc_trade_pnl(cfg, ExitOB)

        assert isclose(res, tv.CALC_TRADE_PNL_RES)

    @unittest.skipIf(skip_test["calc_min_notl"], skip_reason)
    def test_calc_min_notl(self):
        cfg=tv.CALC_MIN_NOTL["CFG"]
        ob_f = tv.CALC_MIN_NOTL["ORDBK_F"]

        #case 1: insufficient OB liquidity on ETHUSDZ25 
        res1 = cc.calc_min_notl(cfg, ob_f, "long")
        #case 2: sufficinet OB liquidity
        res2 = cc.calc_min_notl(cfg, ob_f, "short")

        exp_res = tv.CALC_MIN_NOTL_RES
        
        assert (
            res1 == exp_res["case1"] and
            res2 == exp_res["case2"]
        )
    
    @unittest.skipIf(skip_test["det_notl_dir"], skip_reason)
    def test_det_notl_dir(self):
        t = "ETHZ25"
        
        #case 1: Buy notional for ETHZ25
        res1 = cc.det_notl_dir(t, 100, 200, "Buy")

        #case 2: Sell notional for ETHZ25
        res2 = cc.det_notl_dir(t, 100, 200, "Sell")

        assert (
            res1 == 200  and
            res2 == 100
        )