from custom_bitmex_websocket import BitMEXWebsocket
import logging
from util.subscriptions import TICKER_SUBS
logger = logging.getLogger(__name__)


tickers = ["ETHZ25"]
indices = [".BXBT", ".BETH"]
ws = BitMEXWebsocket(endpoint="wss://ws.bitmex.com/realtime", symbol=tickers,
                         api_key=None, api_secret=None, subscriptions=TICKER_SUBS)
ws.send_command('subscribe',['instrument:.BETH'])
while(ws.ws.sock.connected):
        for s in [tickers]:
                print(ws.get_instrument(s))
        ws.exit()
