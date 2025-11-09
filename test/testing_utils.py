import requests
import time
from datetime import datetime, timedelta
from collections import deque

def get_test_data(symbol, startTime, endTime, interval, ts_format, marker=None):
    """
    Helper function to stage initial data for cfg["ref_prices"]
    """
    def get_stop_time(end, interval):
            """
            Sub-function that gets stop time
            """
            intvl_unit = None
            for c in ("m","h","d"):
                i = interval.find(c)
                if i!=-1:
                    intvl_unit=c
                    break
            if intvl_unit is None:
                raise Exception("No unit was specified in update_interval. i.e. 'm', 'h', 'd'")
            else:
                intvl_num = int(interval.replace(intvl_unit, ""))
                if intvl_unit == "m":
                    return end-timedelta(minutes=intvl_num)
                elif intvl_unit == "h":
                    return end-timedelta(hours=intvl_num)
                else:
                    return end-timedelta(days=intvl_num)
    
    columns = '["timestamp", "bidPrice", "askPrice"]'
    all_res = []
    stop = get_stop_time(endTime, interval)
    while(startTime < stop):
        try:
            url = f"https://www.bitmex.com/api/v1/quote/bucketed?binSize={interval}&symbol={symbol}&startTime={startTime}&endTime={endTime}&columns={columns}&reverse=false"
            res = requests.get(url)
            startTime = datetime.strptime(res.json()[-1]['timestamp'], ts_format)
            all_res.extend(res.json())
            #print(res.headers)
        except KeyError:
            print(res.json(), startTime)
            time.sleep(60) #wait to refresh request limit
        except IndexError:
            print(f"Index Error at {startTime}")
            break
            #return res
    #marker to indicate origin of data points
    if marker is not None:
        for i in range(0, len(all_res)):
            all_res[i].update({"marker":marker})
    return all_res

def dict_to_set(ref_prices):
    """
    Helper function to convert collection of dicts into set of tuples
    """
    return {tuple(d.items()) for d in ref_prices}

def format_deque(cfg, dp=6):
    """
    Helper function to format proc.cfg after proc.is_triggered runs.
    Converts ref_prices and ref_signals data to deque and round signal values to desired dp.
    """
    for t in ("A", "B"):
        cfg["ref_prices"][t] = deque(cfg["ref_prices"][t])
    
    for dir in ("long", "short"):
        cfg["ref_signals"][dir]["data"] = deque(map(lambda v: round(v, dp), cfg["ref_signals"][dir]["data"]))

    
    return cfg