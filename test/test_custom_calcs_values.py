CALC_REF_SIGNAL = {
    "ETHZ25":{
        "portfolio":"A",
        "rel_direction":1,
        "ref_prices":[{"askPrice":2,"bidPrice":1}, {"askPrice":2,"bidPrice":1}],
    },
    "ETHUSDZ25":{
        "portfolio":"B",
        "rel_direction":1,
        "ref_prices":[{"askPrice":2,"bidPrice":1}, {"askPrice":4,"bidPrice":5}],
    },
    "XBTZ25":{
        "portfolio":"B",
        "rel_direction":-1,
        "ref_prices":[{"askPrice":8,"bidPrice":1}, {"askPrice":2,"bidPrice":16}],
    }
}

CALC_REF_SIGNAL_RES = (
    [0.5,4],
    [16,0.8]
)

GET_SZINUSD = {
    "CFG": {
        "ticker_info": {
            "ETHZ25":{
            "contract_sz": {"qty":0.00001, "ccy":"ETH"}
            },
        "ETHUSDZ25":{
            "contract_sz": {"qty":1, "ccy":"0.000001 BTC per USD of contract price"}
            },
        "XBTZ25":{
            "contract_sz": {"qty":1, "ccy":"USD"}
            }
        },
    "index_info":{
        ".BETH": 4485,
        ".BXBT": 124000
        }
    }
}

GET_SZINUSD_RES = [0.0897, 1163.368, 2]

GET_PNLINUSD_RES = [-62, -6.2, -50]

FORMAT_ORDBOOK =[ #Buy and Side orders are intentionally jumbled here
    {
        "symbol":"ETHZ25",
        "side":"Buy",
        "size":2000,
        "price":0.03775,
    },
    {
        "symbol":"ETHZ25",
        "side":"Sell",
        "size":1000,
        "price":0.03845
    },
    {
        "symbol":"ETHZ25",
        "side":"Sell",
        "size":2000,
        "price":0.03814,
    },
    {
        "symbol":"ETHZ25",
        "side":"Buy",
        "size":1000,
        "price":0.03807,
    },
    {
        "symbol":"ETHZ25",
        "side":"Sell",
        "size":1000,
        "price":0.03813,
    },
    {
        "symbol":"ETHZ25",
        "side":"Buy",
        "size":1000,
        "price":0.03806,
    }
]

FORMAT_ORDBOOK_RES = [
    {
        "symbol":"ETHZ25",
        "side":"Buy",
        "size":1000,
        "price":0.03807,
        "sizeUSD": 44.85
    },
    {
        "symbol":"ETHZ25",
        "side":"Buy",
        "size":1000,
        "price":0.03806,
        "sizeUSD": 44.85
    },
    {
        "symbol":"ETHZ25",
        "side":"Buy",
        "size":2000,
        "price":0.03775,
        "sizeUSD": 89.7,
    },
    {
        "symbol":"ETHZ25",
        "side":"Sell",
        "size":1000,
        "price":0.03845,
        "sizeUSD": 44.85
    },
    {
        "symbol":"ETHZ25",
        "side":"Sell",
        "size":2000,
        "price":0.03814,
        "sizeUSD": 89.7
    },
    {
        "symbol":"ETHZ25",
        "side":"Sell",
        "size":1000,
        "price":0.03813,
        "sizeUSD": 44.85
    }
]

OPTIMISE_NUM_LOTS = {
    "CFG": {
        "ticker_info": {
            "ETHZ25":{
            "lot_sz":1000
            },
        "ETHUSDZ25":{
            "lot_sz":1
            },
        "XBTZ25":{
            "lot_sz":100
            }
        }
    }
}

CALC_IMPACT_PX_RES = {
    "case1": (0.038065, 2000, 89.7),
    "case2": (0.038135, 2000, 89.7),
    "case3": (0.0379075, 4000, 179.4)
}

CALC_TICKER_PNL = {
    "CFG":{
        "ticker_info": {
            "ETHZ25":{
            "contract_sz": {"qty":0.00001, "ccy":"ETH"}
            }
        },

        "index_info":{
            ".BXBT": 124000
        },

        "position":{
            "state": None,
            "ETHZ25":{
                "avgPx":0.0390,
                "qty":2000,
                "notionalUSD":90,
                "exitOrdBk_side_per_entry_state": {
                    "long":"Buy",
                    "short": "Sell"
                }
            }
        }
    }
}

CALC_TICKER_PNL_RES = {
    "case1":-2.3188,
    "case2":2.1452
}

CALC_TRADE_PNL = {
    "CFG":{
        "leverage":2,

        "ticker_list":["ETHZ25", "XBTZ25"],

        "ticker_info": {
            "ETHZ25":{
                "contract_sz": {"qty":0.00001, "ccy":"ETH"}
            },
            "XBTZ25":{
                "contract_sz": {"qty":1, "ccy":"USD"}
            },
        },
        
        "index_info":{
            ".BXBT": 124000
        },

        "position":{
            "state": "long",
            "ETHZ25":{
                "avgPx":0.0390,
                "qty":2000,
                "notionalUSD":90,
                "exitOrdBk_side_per_entry_state": {
                    "long":"Buy",
                    "short": "Sell"
                }
            },
            "XBTZ25":{ #This is a copy of ETHZ25 position, but different notionalUSD and flipped exitOrdBk sides
                "avgPx":0.0390,
                "qty":2000,
                "notionalUSD":100,
                "exitOrdBk_side_per_entry_state": {
                    "long":"Sell",
                    "short": "Buy"
                }
            }
        }
    }
}

CALC_TRADE_PNL_RES = 2*(-0.5888/190)

CALC_MIN_NOTL = {
    "CFG":{
        "notional": 1000,
        "ticker_list":["ETHZ25", "ETHUSDZ25"],
    },
    "ORDBK_F":{
        "ETHZ25":[
            {"side":"Buy", "sizeUSD": 500},
            {"side":"Buy", "sizeUSD": 500},
            {"side":"Sell", "sizeUSD": 500},
            {"side":"Sell", "sizeUSD": 500},
        ],
        "ETHUSDZ25":[
            {"side":"Buy", "sizeUSD": 100},
            {"side":"Buy", "sizeUSD": 100},
            {"side":"Sell", "sizeUSD": 500},
            {"side":"Sell", "sizeUSD": 500},
        ]
    }
    
}

CALC_MIN_NOTL_RES = {
    "case1":200,
    "case2":1000
}