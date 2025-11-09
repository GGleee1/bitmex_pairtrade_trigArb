from noti_precan import O_L, O_S, TP_L, TP_S, SL_L, SL_S
from util import log_setter as lset
from datetime import datetime, timedelta
from statistics import mean, stdev
from collections import deque
import requests
import time
import threading


logger = lset.create_logger('bot.py', filename='trade.log')
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
        self.cfg=cfg
        self.OM = OM #OM is an instance of class OrderMgr.
        self.webhook = webhook 
        self.A_fresh = threading.Event()
        self.B_fresh = threading.Event()

        #Check if reference prices need to be updated
        try:
            ts = datetime.strptime(self.cfg["last_update"], self.cfg["timestamp_format"])
        
        except TypeError:
            if self.cfg["last_update"] is None: #indicates fresh config, bootstrap fully
                logger.info("Bootstrapping reference prices for entire window")
                self.cfg["ref_prices"], self.cfg["last_update"]= self._bootstrap_ref_prices()

            else:
                logger.error("Error during processor.init: last_update data type must be None or string of datetime")
                raise TypeError("last_update must be None or string of datetime")

        except ValueError:
            logger.error("Error during processor.init: last_update timestamp format does not match cfg timestamp_format")
            raise ValueError("last_update format does not match timestamp_format")
   
        else: 
            if ts <= (datetime.now()+timedelta(days= -self.cfg["window_size"], hours=-8)):#8hours adjustment of datetime.now() from your tz to BitMex tz 
            #indicates completely outdated reference prices, bootstrap fully
                logger.info("Bootstrapping reference prices for entire window")
                self.cfg["ref_prices"], self.cfg["last_update"] = self._bootstrap_ref_prices()
            else: #indicates partially outdated reference prices
                logger.info("Bootstrapping reference prices for partial window")
                update_vals, self.cfg["last_update"] = self._bootstrap_ref_prices(start = ts)
                last_update_ts = datetime.strptime(self.cfg["last_update"], self.cfg["timestamp_format"])
                #remove older values outside window
                self.cfg["ref_prices"]["A"] = [i for i in self.cfg["ref_prices"]["A"] if datetime.strptime(i["timestamp"],self.cfg["timestamp_format"]) >= (last_update_ts-timedelta(days=self.cfg["window_size"]))]
                self.cfg["ref_prices"]["B"] = [i for i in self.cfg["ref_prices"]["B"] if datetime.strptime(i["timestamp"],self.cfg["timestamp_format"]) >= (last_update_ts-timedelta(days=self.cfg["window_size"]))]
                #append new values
                self.cfg["ref_prices"]["A"].extend(update_vals["A"])
                self.cfg["ref_prices"]["B"].extend(update_vals["B"])
            
            #convert list to deque for O(1) pop and appends
            self.cfg["ref_prices"]["A"] = deque(self.cfg["ref_prices"]["A"])
            self.cfg["ref_prices"]["B"] = deque(self.cfg["ref_prices"]["B"])

        if not (self.cfg["ref_prices"]["A"] and self.cfg["ref_prices"]["B"]): #either or both ref_price is empty deque
            logger.error("Either or both of 'A', 'B' is empty in cfg['ref_price']. Check if supplied ticker is expired or requested time range is correct")
            raise Exception("Either or both of 'A', 'B' is empty in cfg['ref_price']. Check if supplied ticker is expired or requested time range is correct")
        else:
            logger.info("Calculating reference signals and their mean & std")
            short_sig, long_sig = self._get_ref_signal(self.cfg["ref_prices"]["A"],self.cfg["ref_prices"]["B"]) #update cfg["ref_signals"]
            self.cfg["ref_signals"]["short"]["data"] = deque(short_sig)
            self.cfg["ref_signals"]["long"]["data"] = deque(long_sig)  
            self._update_ref_stats("short") #Then, update mean and std of ref_signals
            self._update_ref_stats("long")
        logger.info("processor.init SUCCESS")

    def update_impact_prices(self, msg): #takes in orderbook levels from bitmex websocket. i.e. msg = ws.market_depth(ticker)
        notional = self.cfg["notional"]

        if len(msg)<=1:
            raise Exception("Orderbook only has one or no order")
        else:
            msg.sort(key = lambda m:(m['side'], -m['price'])) #some buy and sell levels are mixed in the list, sort them first. Then sort prices
            #'side' is sorted to have 'sell' after 'buy'. 
            #This makes sorted 'price' accessible in desc order from msg[0] for buy orders, and in asc order from msg[-1] for sell orders
        
        if msg[0]["symbol"]==self.cfg["A"]:
            t="A"; evt = self.A_fresh
        elif msg[0]["symbol"]==self.cfg["B"]:
            t="B"; evt = self.B_fresh
        else:
            raise Exception("Ticker does not match A or B tickers in cfg")

        if msg[0]['side']=='Sell' or msg[-1]['side']=='Buy': #sort should place 'buy' first and 'sell' last. This means no buy or sell orders present respectively
            raise Exception("Orderbook only has either buy or sell orders")
        else:
            imp_ask, accum_ask = self._calc_impact_px(msg, notional, "Sell")
            imp_bid, accum_bid = self._calc_impact_px(msg, notional, "Buy")
            if accum_ask<notional or accum_bid<notional:
                logger.warning(f"Insufficient orderbook depth for {msg[0]['symbol']} notional ${notional}, notional used is bid: ${accum_ask}, ask: ${accum_bid}")
                #recalculate impact price on the smaller notional used
                if accum_ask < accum_bid:
                    imp_bid, accum_bid = self._calc_impact_px(msg, accum_ask, "Buy")
                elif accum_bid < accum_ask:
                    imp_ask, accum_ask = self._calc_impact_px(msg, accum_bid, "Sell")
                #else: pass #do nothing if accum_bid == accum_ask

        lock.acquire()
        #print(f"acquired lock at {msg[0]['symbol']}, {datetime.now()}")
        self.cfg["tick_impact_px"][t] = {"askPrice":imp_ask,
                                         "bidPrice":imp_bid,
                                         "notional_sz":min(accum_bid, accum_ask),
                                         "timestamp": datetime.strftime(datetime.now()+timedelta(hours=-8),self.cfg["timestamp_format"]) #8hours adjustment from your tz to BitMex tz
                                         }
        evt.set()
        lock.release()
        #logger.info(f"{t} impact prices -- ask:{imp_ask}, bid:{imp_bid}")
        #print(f"released lock at {msg[0]['symbol']}, {datetime.now()}")
        ###Check if its a new day: Save bot.py log file and send to Slack here
        pass
    
    def is_triggered(self):
        self.A_fresh.wait(); self.B_fresh.wait()
        #lock.aquire()

        notional = self.cfg["notional"]
        imp = self.cfg["tick_impact_px"]
        short_sig, long_sig = self._get_ref_signal([imp["A"]], [imp["B"]])
        #Check and execute trade if meet trade criteria
        stats = self.cfg["ref_signals"]
        tr_long = self.cfg["thresholds"]["long"]
        tr_short = self.cfg["thresholds"]["short"]
        state = self.cfg["position"]["state"]
        if state is None:
            #check_long
            if long_sig[0] < stats["long"]["mean"]+tr_long["open_std"]*stats["long"]["std"] and imp["A"]["notional_sz"]==notional:
                #buy pair
                logger.info(O_L); self._noti(O_L)
                trade = self.trade_pair("long", notional)
                if trade:
                    self._update_cfg_position("long", long_sig[0], imp)
                    logger.info(O_L)

            #check_short
            elif short_sig[0] > stats["short"]["mean"]+tr_short["open_std"]*stats["short"]["std"] and imp["A"]["notional_sz"]==notional:
                #sell pair
                logger.info(O_S); self._noti(O_S)
                trade = self.trade_pair("short", notional)
                if trade:
                    self._update_cfg_position("short", short_sig[0], imp)
                    logger.info(O_S)

        elif state == "long":
            #check_stoploss_long
            if self._calc_pnl(self.cfg["position"]["entry_px"], imp) < -self.cfg["thresholds"]["long"]["stoploss_pts"] and imp["A"]["notional_sz"]==notional:
                #order_closePair
                logger.info(SL_L); self._noti(SL_L)
                closed = self.close_pair() 
                if closed:
                    self._reset_cfg_position()
                    logger.info("Long position closed - stop loss.")
                else:
                    self.cfg["position"]["state"] = "Pending Close"
                    logger.info("Pending close of long position - stop loss.")

            #check_takeprofit_long
            elif short_sig[0] > stats["long"]["mean"]+tr_long["takeprofit_std"]*stats["long"]["std"] and imp["A"]["notional_sz"]==notional:
                #order_closePair
                logger.info(TP_L); self._noti(TP_L)
                closed = self.close_pair() 
                if closed:
                    self._reset_cfg_position()
                    logger.info("Long position closed - take profit.")
                else:
                    self.cfg["position"]["state"] = "Pending Close"
                    logger.info("Pending close of long position - take profit.")

        elif state == "short":
            #check_stoploss_short
            if self._calc_pnl(self.cfg["position"]["entry_px"], imp) < -self.cfg["thresholds"]["short"]["stoploss_pts"] and imp["A"]["notional_sz"]==notional:
                #order_closePair
                logger.info(SL_S); self._noti(SL_S)
                closed = self.close_pair() 
                if closed:
                    self._reset_cfg_position()
                    logger.info("Short position closed - stop loss.")
                else:
                    self.cfg["position"]["state"] = "Pending Close"
                    logger.info("Pending close of short position - stop loss.")

            #check_takeprofit_short
            elif long_sig[0] < stats["short"]["mean"]+tr_short["takeprofit_std"]*stats["short"]["std"] and imp["A"]["notional_sz"]==notional:
                #order_closePair
                logger.info(TP_S); self._noti(TP_S)
                closed = self.close_pair() 
                if closed:
                    self._reset_cfg_position()
                    logger.info("Short position closed - take profit.")
                else:
                    self.cfg["position"]["state"] = "Pending Close"
                    logger.info("Pending close of short position - take profit.")

        else: #state == "Pending Close"
            #check all positions closed
            pos = self.OM.get_position_info(isOpen=True)
            if not pos: #empty list returned when no open pos 
                self._reset_cfg_position
                logger.info("Pending orders cleared, position reset to None")

        #Updating reference data
        ts_format = self.cfg["timestamp_format"]
        update_time = min(datetime.strptime(imp["A"]["timestamp"], ts_format), datetime.strptime(imp["B"]["timestamp"], ts_format))
        window_start_ts = datetime.strptime(self.cfg["ref_prices"]["A"][0]["timestamp"], ts_format)
        self.cfg["ref_signals"]["short"]["data"].extend(short_sig)
        self.cfg["ref_signals"]["long"]["data"].extend(long_sig)
        self.cfg["ref_prices"]["A"].extend(imp["A"])
        self.cfg["ref_prices"]["B"].extend(imp["B"])
        
        if update_time >= window_start_ts + timedelta(days=self.cfg["window_size"]):
            self.cfg["ref_signals"]["short"]["data"].popleft() #Popping 0th deque element in O(1)
            self.cfg["ref_signals"]["long"]["data"].popleft()
            self.cfg["ref_prices"]["A"].popleft()
            self.cfg["ref_prices"]["B"].popleft()
        
        self._update_ref_stats("long")
        self._update_ref_stats("short")

        self.cfg["last_update"] = datetime.strftime(update_time, self.cfg["timestamp_format"])

        self.A_fresh.clear(); self.B_fresh.clear()
        #lock.release()
        pass
    
    #Helper methods, to keep as private and/or static.
    def _bootstrap_ref_prices(self, start=None, end=datetime.now()-timedelta(hours=8)): #8hours adjustment from your tz to BitMex tz
        def get_stop_time(update_interval):
            intvl_unit = None
            for c in ("m","h","d"):
                i = update_interval.find(c)
                if i!=-1:
                    intvl_unit=c
                    break
            if intvl_unit is None:
                raise Exception("No unit was specified in update_interval. i.e. 'm', 'h', 'd'")
            else:
                intvl_num = int(update_interval.replace(intvl_unit, ""))
                if intvl_unit == "m":
                    return end-timedelta(minutes=intvl_num)
                elif intvl_unit == "h":
                    return end-timedelta(hours=intvl_num)
                else:
                    return end-timedelta(days=intvl_num)
                
        def get_quotes(ticker, start, end):
            #all_columns = '["timestamp", "symbol", "bidSize", "bidPrice", "askPrice", "askSize"]'
            columns = '["timestamp", "bidPrice", "askPrice"]' #best bid and ask every 5m
            all_res = []

            if start is None: start = end-timedelta(days=self.cfg["window_size"])

            endTime = end.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
            stop = get_stop_time(self.cfg["update_interval"])
            while(start < stop):
                try:
                    logger.info(f"Bootstrapping {ticker}: start {start}, stop {stop}")
                    startTime = start.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
                    url = f"https://www.bitmex.com/api/v1/quote/bucketed?binSize={self.cfg['update_interval']}&symbol={ticker}&startTime={startTime}&endTime={endTime}&columns={columns}&reverse=false"
                    res = requests.get(url)
                    start = datetime.strptime(res.json()[-1]['timestamp'],"%Y-%m-%dT%H:%M:%S.%fZ")
                    all_res.extend(res.json())
                except KeyError:
                    logger.error(f"Encountered KeyError during bootstrap of {ticker} at startTime {startTime}.\n Payload returned: {res.json()}")
                    time.sleep(60) #refresh request limit by pausing before requesting next chunk, applicable to large dataset requests
                except IndexError:
                    logger.error(f"Error on request from {startTime}") #print instead of raising to avoid terminating the program.
                    break
            return all_res, endTime # = final record's timestamp in BitMez tz
        
        A_res, last_update = get_quotes(self.cfg["A"], start, end)
        return (
            {
                "A": A_res,  
                "B": get_quotes(self.cfg["B"], start, end)[0]
            },
            last_update #To update cfg["last_update"]
        )      

    def _get_ref_signal(self, pricesA, pricesB): #pricesA,B are each a list of pairs. Each pair minimally having bid & ask i.e. PricesA = [{bidPrice:123, askPrice:456}]
        #Signal = A/B
        #Short: short A (bid), long B (ask)
        prices = tuple(zip(pricesA, pricesB))
        short_sig= [
            a["bidPrice"]/b["askPrice"] for a,b in prices
        ]
        #Long: long A (ask), short B (bid)
        long_sig= [
            a["askPrice"]/b["bidPrice"] for a,b in prices
        ]
        return (short_sig, long_sig)

    def _update_ref_stats(self, direction):
        data = self.cfg["ref_signals"][direction]["data"]
        self.cfg["ref_signals"][direction]["mean"] = mean(data)
        self.cfg["ref_signals"][direction]["std"] = stdev(data)
        pass

    def _calc_impact_px(self, msg, notional, side):
        if side == "Buy":
            i=0; inc=1
        else: #side =="Sell"
            i=-1; inc=-1    
        accum=0; impact_px=0

        #if insufficient liquidity, calc using smaller notional
        maxDepth = sum(i["size"] if i['side'] == side else 0 for  i in msg)
        if maxDepth < notional:
            notional = maxDepth 
        
        while msg[i]['side']==side:
            if accum+msg[i]['size'] > notional:
                impact_px+=msg[i]['price']*(notional-accum)/notional
                accum=notional
                break
            else:
                accum += msg[i]['size']
                impact_px+=msg[i]['price']*msg[i]['size']/notional
                i+=inc
        return impact_px, accum

    def _calc_pnl(self, pos_px, curr_px): #used to check stoploss, or track pnl. curr_px refers to current impact price observed
        state = self.cfg["position"]["state"]
        if state is None:
            return 0
        elif state == "long": #executable prices are wrt short pair
            A1,B1 = curr_px["A"]["bidPrice"], -curr_px["B"]["askPrice"]
            A0,B0 = -pos_px["A"], pos_px["B"]
        else: #state == "short", executable prices are wrt long pair
            A1,B1 = -curr_px["A"]["askPrice"], curr_px["B"]["bidPrice"] 
            A0,B0 = pos_px["A"], -pos_px["B"]
        pnl = self.cfg["leverage"] * (A0+A1+B0+B1)/(2*curr_px["A"]["notional_sz"]) 
        return pnl
    
    def _update_cfg_position(self, dir, sig, imp):
        self.cfg["position"]["state"] = dir
        self.cfg["position"]["signal"] = sig
        if dir == "short":
            self.cfg["position"]["entry_px"]["A"] = imp["A"]["bidPrice"]
            self.cfg["position"]["entry_px"]["B"] = imp["B"]["askPrice"]
        else: #dir=="long":
            self.cfg["position"]["entry_px"]["A"] = imp["A"]["askPrice"]
            self.cfg["position"]["entry_px"]["B"] = imp["B"]["bidPrice"]
        pass

    def _reset_cfg_position(self):
        self.cfg["position"]={
            "state": None,
            "signal": None,
            "entry_px":{"A": None, "B":None}
        }
        pass
    
    #Noti function to send slack alerts
    def _noti(self, msg):
        if self.webhook is not None:
            payload = '{"text":"%s"}'%msg
            response = requests.post(self.webhook, payload)
            logger.info(f"Slack alert sent. Response code: {response.text}")
        else:
            logger.info("processor.webhook is None, no alert sent")
        pass

    #wrapper to validate trade
    def _validate_trade(fn):
        def cancel_or_close(self, res):
            for r in res:
                if r is None: continue
                if r[0]["ordStatus"] == "New": #cancel open orders
                    self.OM.cancel(r[0]["orderID"])

                elif r[0]["ordStatus"]== "Filled": #close filled orders
                    closeSide = "Buy" if r[0]["side"] == "Sell" else "Sell"
                    self.OM.close(
                        side = closeSide,
                        symbol = r[0]["symbol"]
                    )
                else: 
                    pass #rejected or canceled orders not actionable

        def wrapped(*args, **kwargs):
            self_arg = args[0]
            res = fn(*args, **kwargs)

            if any((r is None) for r in res): #one or both orders failed to send
                cancel_or_close(self_arg, res)
                self_arg._noti("One or both orders in trade_pair failed to send.\nCancelling orders and closing any unpaired positions.")
                return False
            else:                
                if all(r[1]==200 for r in res) and all(r[0]["ordStatus"] == "Filled" for r in res): #both orders sent and filled
                    self_arg._noti("Both orders in trade_pair sent and filled.")
                    return True
                else: 
                    self_arg._noti("Unhandled exception caught in trade_pair.\nManual order & position handling required.")
                    return False       
        return wrapped

    #wrapper to validate close trade. Will not cancel unfilled orders, only retry and notify. 
    def _validate_trade_close(fn):
        def determine_side(cfg_state, t):
            match (cfg_state, t):
                case ("long", "A") | ("short", "B"):
                    return "Sell"
                case ("long", "B") | ("short", "A"):
                    return "Buy"
                case _:
                    pass
        
        #For retry, cannot reuse close_pair as its decorator can get called recursively = infinite notis.
        def resend_ord(self, ok_t=None):
            cfg_state = self.cfg["position"]["state"]
            
            if ok_t is not None: #resend only unsuccessful ticker
                t = ("A", self.cfg["A"]) if ok_t == self.cfg["A"] else ("B", self.cfg["B"]) 
                side = determine_side(cfg_state, t[0])
                self.OM.close(side, t[1])    
            
            else: #resend both tickers
                self.OM.close(determine_side(cfg_state, "A"), self.cfg["A"])
                self.OM.close(determine_side(cfg_state, "B"), self.cfg["B"])         
            pass
        
        def wrapped(*args, **kwargs):
            self_arg = args[0]
            res = fn(*args, **kwargs)
            
            if any((r is None) for r in res):
                self_arg._noti("Some or both orders in close_pair unsent.\nAttempting to resend.\nManual order & position handling required.")
                ok_t = None
                for r in res:
                    if r is None: continue
                    elif r[0]["ordStatus"] == "New" or r[0]["ordStatus"]=="Filled":
                        ok_t = r[0]["symbol"]

                resend_ord(self_arg, ok_t)
                return False

            elif all(r[0]["ordStatus"] == "Filled" for r in res):
                self_arg._noti("Both orders in close_pair sent and filled.")
                return True
            
            elif all((r[0]["ordStatus"] == "Filled") or (r[0]["ordStatus"]=="New") for r in res):
                self_arg._noti("Both orders in close_pair sent, but some orders remain open.\nManual order & position handling required.")
                return False
            
            else:
                self_arg._noti("Some or both orders sent, but status rejected, or cancelled.\nAttempting to resend.\nManual order & position handling required.")
                ok_t = None
                for r in res:
                    if r is None: continue
                    elif r[0]["ordStatus"] == "New" or r[0]["ordStatus"]=="Filled":
                        ok_t = r[0]["symbol"]

                resend_ord(self_arg, ok_t)
                return False
       
        return wrapped    

    @_validate_trade
    def trade_pair(self, direction, notional, a_px=None, b_px=None, extra_attrs = None):
        if direction == "long":
            buy_t = self.cfg["A"]; buy_px = a_px
            sell_t = self.cfg["B"]; sell_px = b_px
        else: #direction == "short"
            buy_t = self.cfg["B"]; buy_px = b_px
            sell_t = self.cfg["A"]; sell_px = a_px
        if extra_attrs:
            threads = [
                ResponsiveThread(target = self.OM.buy, args=(buy_t, notional, buy_px), kwargs={"extra_attrs": extra_attrs}),
                ResponsiveThread(target = self.OM.sell, args=(sell_t, notional, sell_px), kwargs={"extra_attrs": extra_attrs})
                ]
        else:
            threads = [
                ResponsiveThread(target = self.OM.buy, args=(buy_t, notional, buy_px)),
                ResponsiveThread(target = self.OM.sell, args=(sell_t, notional, sell_px))
                ]
        for thread in threads:
            thread.start()
        responses =[]
        for thread in threads:
            responses.append(thread.join())

        return responses
    
    @_validate_trade_close
    def close_pair(self, extra_attrs = None): #Not including feature for notional here, as current design only keeps up to one pair open at any time
        state = self.cfg["position"]["state"]
        open_long_t = self.cfg["A"] if state == "long" else self.cfg["B"]
        open_short_t = self.cfg["A"] if state == "short" else self.cfg["B"]
        
        if extra_attrs:
            threads = [
                ResponsiveThread(target = self.OM.close, args=("Sell", open_long_t), kwargs={"extra_attrs": extra_attrs}),
                ResponsiveThread(target = self.OM.close, args=("Buy", open_short_t), kwargs={"extra_attrs": extra_attrs})
                ]
        else:
            threads = [
                ResponsiveThread(target = self.OM.close, args=("Sell", open_long_t)),
                ResponsiveThread(target = self.OM.close, args=("Buy", open_short_t))
                ]

        for thread in threads:
            thread.start()
        responses =[]
        for thread in threads:
            responses.append(thread.join())

        return responses
    
    """TO DO"""
    #To add feature to update_impact_prices: Check if its a new day: Save bot.py log file and send to Slack via self._noti
    #Consider refactoring code for if-else conditions for opening/closing positions -> implement a rule_factory of sorts
    #OTO order to sell spot XBTUSD when take profit 

    

