# Most subscriptions take a symbol, but some do not.
ACCOUNT_SUBS = [
    "account",
    "affiliate",
    "announcement",
    "connected",
    "chat",
    "margin",
    "publicNotifications",
    "privateNotifications",
    "transact",
    "wallet"
]

INDEX_SUBS = [
    "instrument"
]

TICKER_SUBS =[
    # You can sub to orderBookL2 for all levels, or orderBook10 for top 10 levels.
    # This will save bandwidth & processing time in many cases. OrderBook10 is a pulsed
    # table that sends all rows. For more on orderBook subscriptions, see
    # https://www.bitmex.com/app/wsAPI#Subscriptions
    "orderBookL2_25",
    "instrument"
]

ESSENTIAL ={
    #Must-have subscriptions. Program wil not proceed unless confirmed available.
    "INDEX_SUBS": ["instrument"],
    "TICKER_SUBS": ["orderBookL2_25", "instrument"],
    "ACCOUNT_SUBS": ["margin", "position"]
}
