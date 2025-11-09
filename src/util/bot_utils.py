from util import log_setter as lset
from util import custom_calcs as cc
from datetime import datetime, timedelta
from collections import deque
from statistics import mean, stdev
import requests, time

logger = lset.create_logger('bot.py', filename='trade.log')
logger.propagate = False #disable root logger from directing logs to stream

def update_ref_stats(cfg):
    for d in ("short", "long"):
        data = cfg["ref_signals"][d]["data"]
        cfg["ref_signals"][d]["mean"] = mean(data)
        cfg["ref_signals"][d]["std"] = stdev(data)
    pass

def init_ref_vals(cfg):
    
    tickers = cfg["ticker_list"]
    ticker_info = cfg["ticker_info"]
    last_update = cfg["last_update"]
    ts_format = cfg["timestamp_format"]
    ref_signals = cfg["ref_signals"]
    window_sz = cfg["window_size"]
    end = datetime.now()-timedelta(hours=8)
    update_interv = cfg["update_interval"]

    def bootstrap_ref_prices(start=None, end=datetime.now()-timedelta(hours=8)):
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

            if start is None: start = end-timedelta(days=window_sz)

            endTime = end.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
            stop = get_stop_time(update_interv)
            while(start < stop):
                try:
                    logger.info(f"Bootstrapping {ticker}: start {start}, stop {stop}")
                    startTime = start.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
                    url = f"https://www.bitmex.com/api/v1/quote/bucketed?binSize={update_interv}&symbol={ticker}&startTime={startTime}&endTime={endTime}&columns={columns}&reverse=false"
                    res = requests.get(url)
                    start = datetime.strptime(res.json()[-1]['timestamp'],"%Y-%m-%dT%H:%M:%S.%fZ")
                    all_res.extend(res.json())
                except KeyError:
                    logger.error(f"Encountered KeyError during bootstrap of {ticker} at startTime {startTime}.\n Payload returned: {res.json()}")
                    time.sleep(60) #refresh request limit by pausing before requesting next chunk, applicable to large dataset requests
                except IndexError:
                    logger.error(f"Error on request from {startTime}") #print instead of raising to avoid terminating the program.
                    break
            return all_res
        
        res = {}
        for t in tickers:
            res.update({t: get_quotes(t, start, end)})
        
        return res

    try:
        ts = datetime.strptime(last_update, ts_format)
        
    except TypeError:
        if last_update is None: #indicates fresh config, bootstrap fully
            logger.info("Bootstrapping reference prices for entire window")
            update_vals = bootstrap_ref_prices(end=end)
            for t in tickers:
                cfg["ticker_info"][t]["ref_prices"] = update_vals[t]

        else:
            logger.error("Error during processor.init: last_update data type must be None or string of datetime")
            raise TypeError("last_update must be None or string of datetime")

    except ValueError:
        logger.error("Error during processor.init: last_update timestamp format does not match cfg timestamp_format")
        raise ValueError("last_update format does not match timestamp_format")

    else: 
        if ts <= (datetime.now()+timedelta(days= -window_sz, hours=-8)):#8hours adjustment of datetime.now() from your tz to BitMex tz 
        #indicates completely outdated reference prices, bootstrap fully
            logger.info("Bootstrapping reference prices for entire window")
            update_vals = bootstrap_ref_prices(end=end)
            for t in tickers:
                cfg["ticker_info"][t]["ref_prices"] = update_vals[t]
        
        else:
        #indicates partially outdated reference prices
            logger.info("Bootstrapping reference prices for partial window")
            update_vals = bootstrap_ref_prices(start = ts, end=end)
            last_update_ts = datetime.strptime(last_update, ts_format)
            
            for t in tickers:
                #remove older values outside window
                cfg["ticker_info"][t]["ref_prices"] = [i for i in ticker_info[t]["ref_prices"] if datetime.strptime(i["timestamp"],ts_format) >= (last_update_ts-timedelta(days=window_sz))]

                #append new values
                cfg["ticker_info"][t]["ref_prices"].extend(update_vals[t])
        
                #convert list to deque for O(1) pop and appends
                cfg["ticker_info"][t]["ref_prices"] = deque(cfg["ticker_info"][t]["ref_prices"])
        
        cfg["last_update"] = end.strftime(ts_format)

    if not all([ticker_info[t]["ref_prices"] for t in ticker_info]): #some or all ref_price is empty deque
        logger.error("Some or all tickers' ref_prices are empty in cfg. Check if supplied ticker is expired or requested time range is correct")
        raise Exception("Some or all tickers' ref_prices are empty in cfg. Check if supplied ticker is expired or requested time range is correct")
    
    else:
        logger.info("Calculating reference signals and their mean & std")
        short_sig, long_sig =  cc.calc_ref_signal(ticker_info) #update cfg["ref_signals"]
        ref_signals["short"]["data"] = deque(short_sig)
        ref_signals["long"]["data"] = deque(long_sig)
        update_ref_stats(cfg) #Then, update mean and std of ref_signals
    
    logger.info("processor.init SUCCESS")
    pass

def get_min_imp_ts(cfg):
    min_ts = None
    
    for t in cfg["ticker_list"]:
        ts = datetime.strptime(
            cfg["ticker_info"][t]["impact_px"]["timestamp"],
            cfg["timestamp_format"]
        )
        if min_ts is None or min_ts > ts:
            min_ts = ts
        #else: continue
    return min_ts

def update_ref_vals(cfg):
    tickers = cfg["ticker_list"]
    ti = cfg["ticker_info"]
    w = cfg["window_size"]
    ts_format = cfg["timestamp_format"]

    #calculate incoming signals
    short_sig, long_sig = cc.calc_ref_signal(ti)
    
    #get timestamps for comparison
    imp_ts = get_min_imp_ts(cfg)
    window_ref_ticker = tickers[0]
    window_start_ts = datetime.strptime(
        ti[window_ref_ticker]["ref_prices"][0]["timestamp"],
        ts_format
        )
    
    #update ref_signals
    cfg["ref_signals"]["short"]["data"].extend(short_sig)
    cfg["ref_signals"]["long"]["data"].extend(long_sig)
    #update ref_prices
    for t in tickers:
        cfg["ticker_info"][t]["ref_prices"].extend(
            ti[t]["impact_px"]
        )
    
    #truncate old ref data outside window
    if imp_ts >= window_start_ts + timedelta(days = w):
        cfg["ref_signals"]["short"]["data"].popleft()
        cfg["ref_signals"]["long"]["data"].popleft()
        for t in tickers:
            cfg["ticker_info"][t]["ref_prices"].popleft()

    #update ref_stats
    update_ref_stats(cfg)

    #update last_update timestamp
    cfg["last_update"] = datetime.strftime(imp_ts, ts_format)
    pass

def noti(webhook_url, msg):
    if webhook_url is not None:
        payload = '{"text":"%s"}'%msg
        response = requests.post(webhook_url, payload)
        logger.info(f"Slack alert sent. Response code: {response.text}")
    else:
        logger.info("processor.webhook is None, no alert sent")
    pass