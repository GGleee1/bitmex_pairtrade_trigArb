OB_SIDE_CFG ={ #Reference OB side for entry
    "long": {
        "ETHZ25": "Sell",
        "ETHUSDZ25": "Buy",
        "XBTZ25": "Sell"
    },
    "short": {
        "ETHZ25": "Buy",
        "ETHUSDZ25": "Sell",
        "XBTZ25": "Buy"
    }    
} 

NOTL_DIR_CFG = { #Reference notl side for entry
    "Buy": {
        "ETHZ25": "short",
        "ETHUSDZ25": "long",
        "XBTZ25": "short"
    },
    "Sell":{
        "ETHZ25": "long",
        "ETHUSDZ25": "short",
        "XBTZ25": "long"
    }
}


def calc_ref_signal(ticker_info):
    #ref_prices are each a list of pairs. Each pair minimally having bid & ask i.e. PricesA = [{bidPrice:123, askPrice:456}]
    
    #custom logic
    pricesA = None; pricesB1 = None; pricesB2 = None; pricesB = []

    for t in ticker_info:
        match ticker_info[t]["portfolio"]:
            case "A": #single security for pricesA
                pricesA = ticker_info[t]["ref_prices"]
            case "B":
                if ticker_info[t]["rel_direction"] == 1:
                    pricesB1 = ticker_info[t]["ref_prices"]
                elif ticker_info[t]["rel_direction"] == -1:
                    pricesB2 = ticker_info[t]["ref_prices"]
                else:
                    raise Exception("Unhandled ticker(s) in portfolio B. Check ticekr_info in cfg.")
            case _:
                raise Exception("Unhandled ticker in ticker_info. Check ticker_info in cfg.")

    #custom calc for pricesB
    for b1,b2 in tuple(zip(pricesB1, pricesB2)):
        pricesB.append(
            {
                "bidPrice":b1["bidPrice"]/b2["askPrice"],
                "askPrice":b1["askPrice"]/b2["bidPrice"]
            }
        )

    #Signal = A/B
    #Short: short A (bid A:1, ask A:-1), long B (ask B:1, bid B:-1)
    prices = tuple(zip(pricesA, pricesB))
    
    short_sig= [
        a["bidPrice"]/b["askPrice"] for a,b in prices
    ]
    #Long: long A (ask A:1, bid A:-1), short B (bid B:1, ask B:-1)
    long_sig= [
        a["askPrice"]/b["bidPrice"] for a,b in prices
    ]

    return (short_sig, long_sig)

def get_szInUSD(cfg, ticker):
    #This fn converts size to USD units.
    cont_sz = cfg["ticker_info"][ticker]["contract_sz"]["qty"]
    index = cfg["index_info"]
    match ticker:
        case "ETHZ25":
            calc = lambda num_contracts, price_lvl: num_contracts * cont_sz * index[".BETH"]  
        case "XBTZ25":
            calc = lambda num_contracts, price_lvl: num_contracts * cont_sz
        case "ETHUSDZ25":
            calc = lambda num_contracts, price_lvl: num_contracts * price_lvl * 0.000001 * index[".BXBT"]
        case _:
            raise Exception(f"Unhandled ticker {ticker} in get_szInUSD.")
    return calc

def get_PnLInUSD(cfg, ticker):
    cont_sz = cfg["ticker_info"][ticker]["contract_sz"]["qty"]
    index = cfg["index_info"]
    match ticker:
        case "ETHZ25":
            calc = lambda px_chg, qty: px_chg * qty * cont_sz * index[".BXBT"]  
        case "XBTZ25":
            calc = lambda px_chg, qty: px_chg * qty * cont_sz
        case "ETHUSDZ25":
            calc = lambda px_chg, qty: px_chg * qty * 0.000001 * index[".BXBT"]
        case _:
            raise Exception(f"Unhandled ticker {ticker} in get_PnLInUSD.")
    return calc

def format_ordBook(ordBookData, cfg):
    #Sort orderbook levels.
    #BitMex orderBookData gives size in num. of contracts, convert to USD.
    
    ordBookData.sort(key = lambda m:(m['side'], -m['price'])) 
        #some buy and sell levels are mixed in the list, sort them first. Then sort prices
        #'side' is sorted to have 'sell' after 'buy'. 
        #This makes sorted 'price' accessible in desc order from msg[0] for buy orders, and in asc order from msg[-1] for sell orders

    ticker =ordBookData[0]["symbol"]
    calc = get_szInUSD(cfg, ticker)
    
    for i in ordBookData:
        i.update({"sizeUSD":calc(i["size"], i["price"])})

    return ordBookData

def optimise_num_lots(cfg, ordBkLevel, USDtoFill):
    ticker = ordBkLevel['symbol']
    lot_sz =cfg["ticker_info"][ticker]["lot_sz"]
    
    USDperLot = lot_sz * ordBkLevel['sizeUSD']/ordBkLevel['size']
    lots_to_fill = USDtoFill/USDperLot
    
    if (lots_to_fill-int(lots_to_fill)) >= 0.5:
        lots_to_fill+=1

    return int(lots_to_fill)*lot_sz

def calc_impact_px(cfg, ordBk_f_t, notionalUSD, side): #ordBk_f_t is formatted orderBook of one ticker
        if side == "Buy":
            i=0; inc=1
        else: #side =="Sell"
            i=-1; inc=-1
            
        accumUSD=0; accumCont=0; numerator = 0
        #impact_px = numerator/accumCont
        #numerator = price * size in contract units

        while ordBk_f_t[i]['side']==side:
            if accumUSD+ordBk_f_t[i]['sizeUSD'] > notionalUSD-accumUSD:
                #optimise num lots to order
                num_conts = optimise_num_lots(cfg, ordBk_f_t[i], notionalUSD-accumUSD)

                accumUSD += ordBk_f_t[i]['sizeUSD']*num_conts/ordBk_f_t[i]["size"]
                accumCont += num_conts
                numerator += ordBk_f_t[i]['price']*num_conts
                break
            
            else:
                accumUSD += ordBk_f_t[i]['sizeUSD']
                accumCont += ordBk_f_t[i]['size']
                numerator += ordBk_f_t[i]['price']*ordBk_f_t[i]['size']
                i+=inc

        return numerator/accumCont, accumCont, accumUSD #impact price, size to order

def calc_ticker_pnl(cfg, ticker, ExitOB_t): #ExitOB is formatted orderBook of one ticker
    qty = cfg["position"][ticker]["qty"]
    pos_state = cfg["position"]["state"]
    entry_px = cfg["position"][ticker]["avgPx"]

    #custom close instructions per ticker encoded in cfg
    exitOrdBk_side = cfg["position"][ticker]["exitOrdBk_side_per_entry_state"][pos_state]

    #This is same logic as calc_impact_px but size is in contracts, not USD
    if exitOrdBk_side == "Buy":
        i=0; inc=1
    else: #side =="Sell"
        i=-1; inc=-1
    accumQty = 0; numerator = 0
    while ExitOB_t[i]['side']==exitOrdBk_side:
            if accumQty + ExitOB_t[i]['size'] > qty-accumQty:
                numerator += ExitOB_t[i]['price']*(qty-accumQty)
                break
            
            else:
                accumQty += ExitOB_t[i]['size']
                numerator += ExitOB_t[i]['price']*ExitOB_t[i]['size']
                i+=inc

    exit_px = numerator/qty

    #If looked at "Buy" orders of orderBook, this was a long ticker position now selling to close
    if exitOrdBk_side == "Buy":
        px_chg = exit_px-entry_px

    #If looked at "Sell" orders of orderBook, this was a short ticker position now buying to close
    else: #exitOrdBk_side == "Sell"
        px_chg = entry_px-exit_px
    
    #PnL in USD
    calc = get_PnLInUSD(cfg, ticker)
    
    return calc(px_chg, qty)
    
def calc_trade_pnl(cfg, ExitOB):
    abs_PnL = 0
    entry_notional = 0
    for t in cfg["ticker_list"]:
        abs_PnL += calc_ticker_pnl(cfg, t, ExitOB[t])
        entry_notional += cfg["position"][t]["notionalUSD"]
    return cfg["leverage"]*abs_PnL/entry_notional #assuming all tickers have same leverage

#if insufficient liquidity, use smaller notional
def calc_min_notl(cfg, ordBk_f, direction): #ordBk_f is formatted orderbook of all tickers
    notional = cfg["notional"]
    bs = OB_SIDE_CFG
    
    for t in cfg["ticker_list"]:
        maxDepth = sum(i["sizeUSD"] if i['side'] == bs[direction][t] else 0 for i in ordBk_f[t])
        if maxDepth < notional:
            notional = maxDepth
    return notional

def det_notl_dir(t, notl_long, notl_short, side):
    if NOTL_DIR_CFG[side][t] == "long":
        return notl_long
    else: #"short"
        return notl_short
    
    

"""
#Old function to calculate min notional per trade
def get_common_qty(cfg, direction, ordBk_f):
    ti = cfg["ticker_info"]
    ab = ASKBID_CFG[direction]
    
    min_szUSD = min(
        [ti[t]["impact_px"]["notional_sz"][ab[t]] for t in cfg["ticker_list"]]
    )

    res = {}
    for t in cfg["ticker_list"]:
        
        szCont = calc_impact_px(
            cfg,
            ordBk_f,
            min_szUSD,
            side="Buy" if ab[t] == "USD_bid" else "Sell"
        )[1]

        res.update({t: szCont})
    
    return res
"""