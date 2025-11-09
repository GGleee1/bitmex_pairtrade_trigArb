#pip install bitmex-ws
#https://github.com/BitMEX/api-connectors/tree/master/official-ws/python

#Subscriptions available: https://www.bitmex.com/app/wsAPI

#Modified __get_url private method in bitmex_websocket.py to handle multiple tickers
#BitMexWebsocket.data now contains dicts of symbol-specific data. Methods are modified accordingly.

from custom_bitmex_websocket import BitMEXWebsocket
from util import log_setter as lset
from time import sleep
import logging
import threading
import bot_v2 as bot
import my_order_mgr
import json
from credentials import APIKEY, APISECRET, ACCOUNTID, WEBHOOK

logger = lset.create_logger('bitmex_ws.py', filename='start_up.log', filemode='w')
logger.propagate = False #disable root logger from directing logs to stream

# Basic use of websocket.
def run(tickers, cfg, OM, webhook=WEBHOOK):

    proc = bot.processor(cfg, OM, webhook)

    ###For testing purposes###
    #proc.OM.postOnly = True #set True if simulating order placement, but not actually sending.
    #def mock_validate(fn):
    #    def wrapped(*args, **kwargs):
    #        fn(*args, **kwargs)
    #        return True
    #    return wrapped
    #proc._validate_trade = mock_validate
    #proc._validate_trade_close = mock_validate


    indices = list(cfg["index_info"].keys())
    symbols = tickers + indices if indices else tickers

    # Instantiating the WS will make it connect. Be sure to add your api_key/api_secret.
    ws = BitMEXWebsocket(endpoint="wss://ws.bitmex.com/realtime", symbol=symbols,
                         api_key=None, api_secret=None) #testnet: wss://ws.testnet.bitmex.com/realtime #live: wss://ws.bitmex.com/realtime

    for s in symbols:
        logger.info("Instrument data: %s" % ws.get_instrument(s))
    
    logger.info("Websocket connected, all subscriptions live")
    
    #At this point, all components of system should have started up.
    #Save a snapshot of cfg initial state to logs. Write log to disk.
    logger.info(f"Initial cfg state: {proc.cfg}")
    for filehandler in logger.handlers:
        filehandler.flush()

    threads= []
    # Run forever
    while(ws.ws.sock.connected):
        if indices:
            for i in indices: #update index level before calc new impact px
                msg_in = threading.Thread(target=proc.update_index, args=(ws.get_instrument(i),))
                threads.append(msg_in)

        for t in tickers:
            msg_in = threading.Thread(target = proc.update_impact_prices, args=(ws.market_depth(t),))
            threads.append(msg_in)
            
            ###for writing large example message output to file
            """
            f = open("out.txt", 'w')
            json.dump(ws.market_depth(t), f)
            f.close()
            """
            
            ###Some subscriptions available. Configure them in util.subscriptions
            #logger.info("Market Depth: %s" % ws.market_depth(t))
            #logger.info("Recent Trades: %s\n\n" % ws.recent_trades(t))
            #logger.info("Ticker: %s" % ws.get_ticker(t))
        
        threads.append(threading.Thread(target=proc.set_min_notionals))
        #threads.append(threading.Thread(target=proc.is_triggered))

        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        threads.clear()

        """
        if ws.api_key:
            logger.info("Funds: %s" % ws.funds())
        """

        sleep(10)

if __name__ == "__main__":
    #subscriptions = [] #custom subs not fully implemented yet. Changes to subs require changing keys in BitMEXWebsocket class.
    with open("cfg.json", 'r') as f:
        cfg = json.load(f) #cfg is a .json file containing strategy parameters and last updated state
    logger.info("cfg.json loaded")

    tickers = cfg["ticker_list"]
    logger.info("tickers loaded")

    orderIDPrefix = 'ETHXBT_trig_'
    OM = my_order_mgr.OrderMgr(
        base_url = "https://testnet.bitmex.com/api/v1/", #testnet url: https://testnet.bitmex.com/api/v1/ #live url: https://www.bitmex.com/api/v1/
        apiKey = APIKEY,
        apiSecret = APISECRET,
        orderIDPrefix = orderIDPrefix
    )

    logger.info(f"order manager loaded. orderIDPrefix: {orderIDPrefix}")

    OM.set_cross_asset_margin(ACCOUNTID, multi=True)
    logger.info("cross margin enabled")
    for t in tickers:
        OM.set_margin_type(t)
        OM.set_crossLeverage(t,cfg["leverage"])
        logger.info(f'Leverage set for {t}: {cfg["leverage"]}')

    logger.info("Run started")
    run(tickers, cfg, OM)


    """TO DO"""
    #To add periodic check on time. If new period, save trade.log, cfg (pickled), and csv of cfg signals & impact prices to disk
    #Configure a CRON job to send these files to Slack
