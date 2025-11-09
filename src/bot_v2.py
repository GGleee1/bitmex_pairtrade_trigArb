from util import bot_utils as botu
from util import custom_calcs as cc
from util import trigger_rules as trig
from datetime import datetime, timedelta
import threading, logging


logger = logging.getLogger('bot.py')
logger.propagate = False #disable root logger from directing logs to stream

lock = threading.Lock()

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

class processor:
    def __init__(self, cfg, OM, webhook=None): #cfg was a .json file. It is parsed into dict before input here.
        self.cfg = cfg
        self.OM = OM #OM is an instance of class OrderMgr.
        self.webhook = webhook 
        
        self.orderBook = dict()
        self.min_notl_long = None
        self.min_notl_short = None

        self.ticker_fresh = {t : threading.Event() for t in cfg["ticker_list"]}
        self.index_rdy = {i : threading.Event() for i in cfg["index_info"]}
        self.ordBook_rdy = {t : threading.Event() for t in cfg["ticker_list"]}
        self.min_notionals_rdy = threading.Event()
        
        botu.init_ref_vals(self.cfg)
    
    def set_min_notionals(self):
        for t in self.cfg["ticker_list"]:
            self.ordBook_rdy[t].wait()
        lock.acquire()
        self.min_notl_short = cc.calc_min_notl(self.cfg, self.orderBook, "short")
        self.min_notl_long = cc.calc_min_notl(self.cfg, self.orderBook, "long")    
        self.min_notionals_rdy.set()
        lock.release()

    def update_index(self, msg):
        lock.acquire()
        index = msg['symbol']
        self.cfg["index_info"][index] = msg["lastPrice"]
        #logger.info(self.cfg["index_info"])
        self.index_rdy[index].set()
        lock.release()

    def update_impact_prices(self, msg): #takes in orderbook levels from bitmex websocket. i.e. msg = ws.market_depth(ticker)
        if len(msg)<=1:
            #send noti
            raise Exception("Orderbook only has one or no order")

        t = msg[0]["symbol"]

        lock.acquire()
        self.orderBook.update({t: cc.format_ordBook(msg, self.cfg)})
        if self.orderBook[t][0]['side']=='Sell' or self.orderBook[t][-1]['side']=='Buy': #sort should place 'buy' first and 'sell' last. This means no buy or sell orders present respectively
            #send noti
            raise Exception("Orderbook only has either buy or sell orders")
        
        else:
            self.ordBook_rdy[t].set()
        lock.release()

        for i in self.cfg["index_info"]:
            self.index_rdy[i].wait()
        
        self.min_notionals_rdy.wait()

        notl_dir = lambda s: cc.det_notl_dir(
            t,
            self.min_notl_long,
            self.min_notl_short,
            s)

        imp_ask, sz_cont_ask, sz_USD_ask = cc.calc_impact_px(
            self.cfg,
            self.orderBook[t],
            notl_dir("Sell"),
            "Sell")
        
        imp_bid, sz_cont_bid, sz_USD_bid = cc.calc_impact_px(
            self.cfg,
            self.orderBook[t],
            notl_dir("Buy"),
            "Buy")

        lock.acquire()
        #print(f"acquired lock at {msg[0]['symbol']}, {datetime.now()}")
        self.cfg["ticker_info"][t]["impact_px"] = {"askPrice":imp_ask,
                                         "bidPrice":imp_bid,
                                         "notional_sz":{
                                             "USD_ask": sz_USD_ask,
                                             "USD_bid": sz_USD_bid,
                                             "Cont_ask": sz_cont_ask,
                                             "Cont_bid": sz_cont_bid
                                         },
                                         "timestamp": datetime.strftime(datetime.now()+timedelta(hours=-8),self.cfg["timestamp_format"]) #8hours adjustment from your tz to BitMex tz
                                         }
        self.ticker_fresh[t].set()
        lock.release()
        #logger.info(f"{t} impact prices -- ask:{imp_ask}, bid:{imp_bid}")
        #print(f"released lock at {msg[0]['symbol']}, {datetime.now()}")
        ###Check if its a new day: Save bot.py log file and send to Slack here
        pass

    def is_triggered(self):

        for t in self.cfg["ticker_list"]:
            self.ticker_fresh[t].wait() #threading.Event() is IO blocking. Iters next in loop only after event set. 
        
        short_sig, long_sig = cc.calc_ref_signal(self.cfg["ticker_info"])
        trigger = trig.check_trigger(self.cfg, short_sig, long_sig, self.orderBook)
        if trigger:
            message = f"Attempting {trigger}"
            success = f"{trigger} successful"

        match trigger:
            case "openLong":
                if trig.check_min_qty(self.cfg, "long"):
                    logger.info(message); botu.noti(self.webbook, message)
                    trades =self.trade_pair("long")
                if trades:
                    self.update_cfg_position(trades, "long")
                    logger.info(success); botu.noti(self.webbook, success)

            case "openShort":
                if trig.check_min_qty(self.cfg, "short"):
                    logger.info(message); botu.noti(self.webbook, message)
                    trades =self.trade_pair("short")
                if trades:
                    self.update_cfg_position(trades, "short")
                    logger.info(success); botu.noti(self.webbook, success)

            case "stopLossLong"|"takeProfitLong"|"stopLossShort"|"takeProfitShort":
                logger.info(message); botu.noti(self.webbook, message)
                closed = self.close_pair()
                if closed:
                    self.reset_cfg_position()
                    logger.info(success); botu.noti(self.webbook, success)
                else:
                    self.cfg["position"]["state"] = "pendingClose"


            case "pendingClose":
                pos = self.OM.get_position_info(isOpen=True)
                if not pos: #empty list returned when no open pos 
                    self.reset_cfg_position()
                    logger.info("Pending orders cleared, position reset to None")
            case None:
                pass
            
            case _:
                logger.info("Unhandled value returned from trigger_rules.check_trigger")
        
        #update ref_vals
        botu.update_ref_vals(self.cfg)

        #unset threading.Event() objects
        for t in self.cfg["ticker_list"]:
            self.ticker_fresh[t].clear()
            self.ordBook_rdy[t].clear()
        
        for i in self.cfg["index_info"]:
            self.index_rdy[i].clear()
        
        self.min_notionals_rdy.clear()
        
        pass

    def reset_cfg_position(self):
        self.cfg["position"]["state"]=None

        for k in self.cfg["position"]:
            if k in self.cfg["ticker_list"]:
                self.cfg["position"].update(
                    {
                        "avgPx":None,
                        "qty":None,
                        "notionalUSD":None
                    }
                )
        pass

    def update_cfg_position(self, trades, state):
        for r in trades:
            symbol = r[0]["symbol"]
            notionalUSD = cc.get_executed_notionalUSD(self.cfg, symbol, state)
            if not notionalUSD:
                logger.info("Unhandled combination of state, portfolio, and relative_direction received from custom_calcs.get_executed_notionalUSD.\nUsing self.min_notl_long/short as next best est.")
                notionalUSD = self.min_notl_long if state=="long" else self.min_notl_short #using next best estimated of notionalUSD traded for that ticker
            else:
                self.cfg["position"][symbol].update(
                    {
                        "avgPx":r[0]["avgPx"],
                        "qty":r[0]["orderQty"],
                        "notionalUSD": notionalUSD
                    }
                )
        pass

    #wrapper to validate trade
    #cancel or close orders are placed in threads to avoid my_order_mgr calling exit(1) from terminating main thread. 
    def _validate_trade(fn):
        def cancel_or_close(self, res):
            for r in res:
                if r is None: continue
                if r[0]["ordStatus"] == "New": #cancel open orders
                    thread = threading.Thread(target = self.OM.cancel, args=(r[0]["orderID"]))
                    thread.start();thread.join()


                elif r[0]["ordStatus"]== "Filled": #close filled orders
                    closeSide = "Buy" if r[0]["side"] == "Sell" else "Sell"
                    thread = threading.Thread(target = self.OM.close, args=(closeSide, r[0]["symbol"]))
                    thread.start();thread.join()

                else: 
                    pass #rejected or canceled orders not actionable

        def wrapped(*args, **kwargs):
            self_arg = args[0]
            res = fn(*args, **kwargs)

            if any((r is None) for r in res): #one or both orders failed to send
                cancel_or_close(self_arg, res)
                botu.noti(self_arg.webhook, "Some orders in trade_pair failed to send.\nCancelling orders and closing any unpaired positions.")
                return False
            else:                
                if all(r[1]==200 for r in res) and all(r[0]["ordStatus"] == "Filled" for r in res): #both orders sent and filled
                    botu.noti(self_arg.webhook, "All orders in trade_pair sent and filled.")
                    return res #True
                else: 
                    botu.noti(self_arg.webhook, "Unhandled exception caught in trade_pair.\nManual order & position handling required.")
                    return False       
        return wrapped

    #wrapper to validate close trade. Will not cancel unfilled orders, only retry and notify.
    #resend orders placed in thread to avoid my_order_mgr calling exit(1) from terminating main thread.  
    def _validate_trade_close(fn):
        #For retry, cannot reuse close_pair as its decorator can get called recursively = infinite notis.
        def resend_ord(self, t):
            state = self.cfg["position"]["state"]
            s = self.cfg["position"][t]["exitOrdBk_side_per_entry_state"][state]
            thread = threading.Thread(target=self.OM.close, args=(s,t))
            thread.start();thread.join()           
            pass
        
        def wrapped(*args, **kwargs):
            self_arg = args[0]
            res = fn(*args, **kwargs)

            if any((r is None) for r in res):
                botu.noti(self_arg.webhook, "Some orders in close_pair unsent.\nAttempting to resend.\nManual order & position handling required.")    
                tickers = set(self_arg.cfg["ticker_list"])
                sent = set(r[0]["symbol"] for r in res if r is not None)
                unsent = tickers.difference(sent)
                for t in unsent:
                    resend_ord(self_arg, t)
                return False

            elif all(r[0]["ordStatus"] == "Filled" for r in res):
                botu.noti(self_arg.webhook, "All orders in close_pair sent and filled.")
                return True
            
            elif all((r[0]["ordStatus"] == "Filled") or (r[0]["ordStatus"]=="New") for r in res):
                botu.noti(self_arg.webhook, "All orders in close_pair sent, but some orders remain open.\nManual order & position handling required.")
                return False
            
            else:
                botu.noti(self_arg.webhook, "Some orders sent, but status rejected, or cancelled.\nAttempting to resend.\nManual order & position handling required.")
                for r in res:
                    if r[0]["ordStatus"] != "New" and r[0]["ordStatus"]!="Filled":
                        resend_ord(self_arg, r[0]["symbol"])
                return False
        
        return wrapped

    @_validate_trade
    def trade_pair(self, direction):
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

    @_validate_trade_close
    def close_pair(self):
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


