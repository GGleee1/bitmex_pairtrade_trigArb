CFG = {
    "ticker_list":["ETHZ25", "ETHUSDZ25", "XBTZ25"],

    "ticker_info":{
        "ETHZ25":{
            "impact_px":{
                "notional_sz":{
                    "Cont_ask": 1000,
                    "Cont_bid": 2000
                    }
                },
            "contract_sz": {"qty":0.00001, "ccy":"ETH"},
            "lot_sz": 1000
        },
        "ETHUSDZ25":{
            "impact_px":{
                "notional_sz":{
                    "Cont_ask": 2,
                    "Cont_bid": 1
                }
            },
            "contract_sz": {"qty":1, "ccy":"0.000001 BTC per USD of contract price"},
            "lot_sz":1
        },
        "XBTZ25":{
            "impact_px":{
                    "notional_sz":{
                    "Cont_ask": 100,
                    "Cont_bid": 200
                    }
            },
            "contract_sz": {"qty":1, "ccy":"USD"},
            "lot_sz": 100
        }
    },

    "position":{
        "state": None,
        "ETHZ25":{
            "exitOrdBk_side_per_entry_state": {
                "long":"Sell",
                "short": "Buy"
            }
        },
        "ETHUSDZ25":{
            "exitOrdBk_side_per_entry_state": {
                "long":"Buy",
                "short": "Sell"
            }
        },
        "XBTZ25":{
            "exitOrdBk_side_per_entry_state": {
                "long":"Sell",
                "short": "Buy"
            }
        }
    }
}

TRADE_NOVALIDATE_LONG = {
    "ETHZ25":1000,
    "ETHUSDZ25":-1,
    "XBTZ25":100
}

TRADE_NOVALIDATE_SHORT = {
    "ETHZ25":-2000,
    "ETHUSDZ25":2,
    "XBTZ25":-200
}

