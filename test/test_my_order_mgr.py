#CLI: python -m unittest test.test_my_order_mgr
import sys
sys.path.append('C:/Users/User/Crypto_PerpFut_Arb/src') #specify the absolute path of bot module here

import unittest

from src import my_order_mgr
from src.credentials import APIKEY, APISECRET, ACCOUNTID

skip_test = {
    "set_margin_type": False,
    "set_crossLeverage": False,
    "set_cross_asset_margin": False,
    "get_position_info": False,
    "orders": False,
    "cancel_and_status": False
}
skip_reason = "As specified in skip_test"

OM = my_order_mgr.OrderMgr(
    base_url = "https://testnet.bitmex.com/api/v1/",
    apiKey= APIKEY,
    apiSecret=APISECRET,
    postOnly=True
)

class TestOM(unittest.TestCase):
    @unittest.skipIf(skip_test["set_margin_type"],reason=skip_reason)
    def test1_set_margin_type(self):
        """
        Test set_margin being able to toggle between isolated and cross margins
        Note: Isolating margin is allowed only if account has sufficient balance in that contract's settlement currency
        """
        can_isolate = OM.set_margin_type("XRPUSDT", isolateMargin=True)
        can_cross = OM.set_margin_type("XRPUSDT") #defaults to cross margin
        self.assertTrue(
            (not can_isolate[0]['crossMargin']) #==False
            and can_cross[0]['crossMargin'] #==True
        )

    @unittest.skipIf(skip_test["set_crossLeverage"],reason=skip_reason)
    def test2_set_crossLeverage(self):
        """
        Test set_crossLeverage able to sets leverage correctly. Verify that setting cross leverage > 0 toggles cross margin on.
        """
        OM.set_margin_type("XRPUSDT", isolateMargin=True)
        response = OM.set_crossLeverage("XRPUSDT", 2)[0]
        self.assertTrue(
            response["crossMargin"] #==True
            and response["leverage"]==2.0
            )
        
    @unittest.skipIf(skip_test["set_cross_asset_margin"],reason=skip_reason)
    def test3_set_cross_asset_margin(self):
        """
        Test set_cross_asset_margin being able to toggle between single asset and multi asset margining
        Note: multi asset margin is only allowed when cross margin is enabled, not allowed on isolated margin
        """
        OM.set_margin_type("XRPUSDT") #multi asset margin requires cross margin
        res_multi = OM.set_cross_asset_margin(ACCOUNTID, multi=True)
        
        res_single = OM.set_cross_asset_margin(ACCOUNTID)

        self.assertTrue(
            res_single[0].get("marginingMode") is None and #key does not exist for single asset
            res_multi[0]["marginingMode"]=="MultiAsset"
        )

    @unittest.skipIf(skip_test["get_position_info"],reason=skip_reason)
    def test4_get_position_info(self):
        """
        Generic test for correct parameters sent to 'position' endpoint
        """
        res = OM.get_position_info({"symbol":"XBTUSD"})
        self.assertTrue(res[1]==200)

    @unittest.skipIf(skip_test["orders"], skip_reason)    
    def test5_buy_market(self):
        """
        Test that OM can execute market buy order
        Note: test5, 6, and 7 are to be tested together in that specific order, to ensure account has no net exposure after testing.
        Note: quantity in test5 != test6 tp ensure non-zero exposure available to be closed in test7, else throws error.
        Note: choice of symbol depends on available orderbook liquidity to test both buy and sell orders.
        Note: quantity set should also comply with lot size requirements of symbol.
        """
        symbol = "XBTUSDT"
        qty = 200
        res = OM.buy(symbol, quantity=qty, price=None)
        self.assertTrue(
            res[0]["orderQty"]==qty
            and res[0]["side"] == "Buy"
            and res[0]["ordType"]=="Market"
            and res[0]["symbol"]==symbol)
    
    @unittest.skipIf(skip_test["orders"], skip_reason)
    def test6_sell_market(self):
        """
        Test that OM can execute market sell order
        Note: see notes from test5
        """
        symbol = "XBTUSDT"
        qty = 100
        res = OM.sell(symbol, quantity=qty, price=None)
        self.assertTrue(
            res[0]["orderQty"]== qty
            and res[0]["side"] == "Sell"
            and res[0]["ordType"]=="Market"
            and res[0]["symbol"]==symbol)

    @unittest.skipIf(skip_test["orders"], skip_reason)
    def test7_close(self):
        """
        Test that OM can close existing position
        Note: see notes from test5
        """
        symbol = "XBTUSDT"
        res = OM.close("Sell", symbol) #since qty buy > sell, set side == "Sell"
        outs = OM.get_position_info({"symbol":symbol})[0][0]["currentQty"]
        self.assertTrue(
            res[0]["execInst"]=="Close"
            and res[0]["symbol"]==symbol
            and outs == 0)
        
    @unittest.skipIf(skip_test["cancel_and_status"], skip_reason)
    def test8_cancel_and_get_execution_status(self):
        """
        Test cancel cancels orders
        Test get_execution_status is tracking orders
        """
        symbol = "XBTUSDT"
        order_res = OM.buy(symbol, quantity=100, price=70000) #send an extremely OTM limit order
        orderID = order_res[0]["orderID"]
        
        res_newOrd = OM.get_execution_status(symbol, orderID)
        res_cancel = OM.cancel(orderID)
        res_canceledOrd = OM.get_execution_status(symbol, orderID)
        self.assertTrue(
            res_newOrd[0][0]["ordStatus"]=="New" and
            res_canceledOrd[0][0]["ordStatus"]=="Canceled" and
            res_cancel[1]==200
        )
