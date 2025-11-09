from custom_calcs import calc_trade_pnl


BID_ASK_CFG = {
    "long":{
        "ETHZ25": "ask",
        "ETHUSDZ25": "bid",
        "XBTZ25": "ask"
    },
    "short":{
        "ETHZ25": "bid",
        "ETHUSDZ25": "ask",
        "XBTZ25": "bid"
    }
}

def check_trigger(cfg, short_sig, long_sig, ExitOB): #TODO: any rules on contract_min <= notional size <= available $?
    state = cfg["position"]["state"]
    stoploss = -cfg["position"][state]["stoploss_pts"]
    long_mean = cfg["ref_signals"]["long"]["mean"]
    short_mean = cfg["ref_signals"]["short"]["mean"]
    long_std = cfg["ref_signals"]["short"]["std"]
    short_std = cfg["ref_signals"]["short"]["std"]
    long_thresh = cfg["thresholds"]["long"]
    short_thresh = cfg["thresholds"]["short"]

    pnl = calc_trade_pnl(cfg, ExitOB)

    if state is None:
        if long_sig[0] < long_mean - long_std * long_thresh["open_std"]:
            return "openLong"
        if short_sig[0] > short_mean + short_std * short_thresh["open_std"]:
            return "openShort"
    
    elif state == "long":
        if pnl < stoploss:
            return "stopLossLong"
        elif short_sig[0] > long_mean + long_std * long_thresh["takeprofit_std"]:
            return "takeProfitLong"

        #else: pass
    elif state == "short":
        if pnl < stoploss:
            return "stopLossShort"
        elif long_sig[0] > short_mean - short_std * short_thresh["takeprofit_std"]:
            return "takeProfitShort"

    elif state == "pendingClose":
        return "pendingClose"
    
    else:
        return None

def check_min_qty(cfg, direction):
    bid_ask = BID_ASK_CFG[direction]
    qty = lambda t, bid_ask: cfg["ticker_info"][t]["impact_px"][f"Cont_{bid_ask}"]
    ti = cfg["ticker_info"]
    return all([qty(t, bid_ask[t]) >= ti[t]["lot_sz"] for t in cfg["ticker_list"]])