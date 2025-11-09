#https://github.com/BitMEX/sample-market-maker/blob/master/market_maker/bitmex.py
"""BitMEX API Connector."""
from __future__ import absolute_import
import requests
import time
import datetime
import json
import base64
import uuid
from APIKeyAuthWithExpires import APIKeyAuthWithExpires
import logging
from enum import Enum

#For deserializing python values to json Enum in 'marginingMode'
class marginModes(str, Enum):
    MULTI = "MultiAsset"

# https://www.bitmex.com/api/explorer/
class OrderMgr(object):

    """BitMEX API Connector."""

    def __init__(self, base_url=None, apiKey=None, apiSecret=None,
                 orderIDPrefix="defaultPrefix", postOnly=False, timeout=6):
        """Init connector."""
        self.base_url = base_url
        self.postOnly = postOnly
        if (apiKey is None):
            raise Exception("Please set an API key and Secret to get started. See " +
                            "https://github.com/BitMEX/sample-market-maker/#getting-started for more information."
                            )
        self.apiKey = apiKey
        self.apiSecret = apiSecret
        if len(orderIDPrefix) > 13:
            raise ValueError("settings.ORDERID_PREFIX must be at most 13 characters long!")
        self.orderIDPrefix = orderIDPrefix
        self.retries = 0  # initialize counter

        # Prepare HTTPS session
        self.session = requests.Session()
        """
        # These headers are always sent
        self.session.headers.update({'user-agent': 'liquidbot-' + constants.VERSION})
        self.session.headers.update({'content-type': 'application/json'})
        self.session.headers.update({'accept': 'application/json'})
        """

        self.timeout = timeout
        self.logger = self.__setup_logger()

    def __setup_logger(self):
        # Prints logger info to terminal
        logger = logging.getLogger()
        logger.setLevel(logging.INFO)  # Change this to DEBUG if you want a lot more info
        ch = logging.StreamHandler()
        # create formatter
        formatter = logging.Formatter(fmt='%(asctime)s - %(levelname)s - %(module)s - %(message)s')
        # add formatter to ch
        ch.setFormatter(formatter)
        logger.addHandler(ch)
        return logger

    #def __del__(self):
    #    self.exit()

    #
    # Authentication required methods
    #
    def authentication_required(fn):
        """Annotation for methods that require auth."""
        def wrapped(self, *args, **kwargs):
            if not (self.apiKey):
                msg = "You must be authenticated to use this method"
                #raise errors.AuthenticationError(msg)
                raise Exception(msg)
            else:
                return fn(self, *args, **kwargs)
        return wrapped

    ### Functions I added
    #do not have to set cross leverage and cross margin every trade. The settings are retained until further change (manual interface or via api)
    @authentication_required
    def set_cross_asset_margin(self, accountID, multi=False):
        path = "user/marginingMode"
        postdict={
            "targetAccountId": accountID,
            "marginingMode":marginModes.MULTI if multi else None #None for single asset, "MultiAsset" for multi asset
        }
        return self._curl_bitmex(path=path, postdict = postdict, verb="POST")

    @authentication_required
    def set_margin_type(self, symbol, isolateMargin=False):
        path = "position/isolate"
        postdict = {
            "symbol": symbol,
            "enabled": isolateMargin
        }
        return self._curl_bitmex(path=path, postdict = postdict, verb="POST")

    @authentication_required
    def set_crossLeverage(self, symbol, leverage):
        path = "position/crossLeverage"
        postdict = {
            "symbol":symbol,
            "leverage":leverage
        }
        return self._curl_bitmex(path=path, postdict = postdict, verb="POST")

    @authentication_required
    def get_position_info(self, filter=None, columns=None, count= None, isOpen = None): #filter = {"symbol":"XBTUSD", "currency":"XBT"} for example. Symbol and margin currency
        path = "position"
        if all(param is None for param in (filter, columns, count)):
            query = None
        else:
            query = {
                "filter": json.dumps(filter),
                "columns": columns,
                "count": count
            }
        res = self._curl_bitmex(path=path, query = query, verb="GET")

        #get open positions only if isOpen = True
        if isOpen:
            return [r for r in res[0] if r['isOpen']]
        else:
            return res

    @authentication_required
    def get_orders(self, symbol, filter=None, columns = None,
                         startTime = None, endTime = None, reverse= False):
        """
        filter = {"open":True} for open orders, {"open": False} for closed orders
        startTime and endTime are datetime objects
        see api explorer for other columns' details
        """
        path = "order"
        query = {
            "symbol": symbol,
            "filter": json.dumps(filter),
            "columns": columns,
            "startTime": json.dumps(startTime, default=str),
            "endTime": json.dumps(endTime, default=str),
            "reverse": reverse
        }
        return self._curl_bitmex(path = path, query = query, verb = "GET")

    @authentication_required
    def get_execution_status(self, symbol, orderID=None):
        """
        Check order status
        """
        path = "order"
        query = {
            "symbol": symbol,
            "filter": json.dumps({
                "orderID": orderID
            })
        }
        return self._curl_bitmex(path=path, query = query, verb="GET")
    
    # Some functions included in base script
    @authentication_required
    def isolate_margin(self, symbol, leverage, rethrow_errors=False):
        """Set the leverage on an isolated margin position"""
        path = "position/leverage"
        postdict = {
            'symbol': symbol,
            'leverage': leverage
        }
        return self._curl_bitmex(path=path, postdict=postdict, verb="POST", rethrow_errors=rethrow_errors)

    @authentication_required
    def buy(self, symbol, quantity, price, extra_attrs = {}): #as price is required arg here, buy sell are limit orders
        """Place a buy order.

        Returns order object. ID: orderID
        """
        return self.place_order(symbol, quantity, price, extra_attrs)

    @authentication_required
    def sell(self, symbol, quantity, price, extra_attrs = {}):
        """Place a sell order.

        Returns order object. ID: orderID
        """
        return self.place_order(symbol, -quantity, price, extra_attrs)
    
    @authentication_required 
    def close(self, side, symbol, extra_attrs={}, quantity=None): 
        attrs = {'execInst': 'Close'} #execInst can contain multiple values, delimited by '%2C%'. e.g. Close%2C%20LastPrice
        attrs.update(extra_attrs)
        if quantity is None:
            postdict = {
                'symbol' : symbol,
                'side' : side,
                'ordType' : "Market",
            }
        else:
            postdict = {
                'symbol' : symbol,
                'orderQty' : quantity,
                'ordType' : "Market",
            }
        postdict.update(attrs)
        # postOnly not allowed for Market ordType
        #if self.postOnly:
        #    postdict['execInst'] = 'ParticipateDoNotInitiate'
        return self._curl_bitmex(path="order", postdict=postdict, verb="POST")


    @authentication_required
    def place_order(self, symbol, quantity, price, extra_attrs = {}):
        """Place an order."""
        if price is not None and price < 0:
            raise Exception("Price must be positive.")
        postdict = {
            'symbol': symbol,
            'orderQty': quantity,
            'price': price,
            # Generate a unique clOrdID with our prefix so we can identify it.
            'clOrdID': self.orderIDPrefix + base64.b64encode(uuid.uuid4().bytes).decode('utf8').rstrip('=\n')
        }
        if price is None:
            postdict.pop('price')
            postdict['ordType'] = "Market"
        elif self.postOnly: #post-only not allowed for Market ordType
            postdict['execInst'] = 'ParticipateDoNotInitiate'
        postdict.update(extra_attrs)
        return self._curl_bitmex(path="order", postdict=postdict, verb="POST")

    @authentication_required
    def amend_order(self, order):
        # Note rethrow; if this fails, we want to catch it and re-tick
        return self._curl_bitmex(path='order', postdict=order, verb='PUT', rethrow_errors=True)

    @authentication_required
    def create_orders(self, orders):
        """Create multiple orders."""
        results = []
        for order in orders:
            results.append(self.place_order(order['orderQty'], order['price'], order))
        return results

    @authentication_required
    def amend_orders(self, orders):
        """Amend multiple orders."""
        results = []
        for order in orders:
            results.append(self.amend_order(order))
        return results

    @authentication_required
    def http_open_orders(self, symbol):
        """Get open orders via HTTP. Used on close to ensure we catch them all."""
        path = "order"
        orders = self._curl_bitmex(
            path=path,
            query={
                'filter': json.dumps({'ordStatus.isTerminated': False, 'symbol': symbol}),
                'count': 500
            },
            verb="GET"
        )
        # Only return orders that start with our clOrdID prefix.
        return [o for o in orders if str(o['clOrdID']).startswith(self.orderIDPrefix)]

    @authentication_required
    def cancel(self, orderID):
        """Cancel an existing order."""
        path = "order"
        postdict = {
            'orderID': orderID,
        }
        return self._curl_bitmex(path=path, postdict=postdict, verb="DELETE")

    @authentication_required
    def withdraw(self, amount, fee, address):
        path = "user/requestWithdrawal"
        postdict = {
            'amount': amount,
            'fee': fee,
            'currency': 'XBt',
            'address': address
        }
        return self._curl_bitmex(path=path, postdict=postdict, verb="POST", max_retries=0)

    def _curl_bitmex(self, path, query=None, postdict=None, timeout=None, verb=None, rethrow_errors=False,
                     max_retries=None):
        """Send a request to BitMEX Servers."""
        # Handle URL
        url = self.base_url + path

        if timeout is None:
            timeout = self.timeout

        # Default to POST if data is attached, GET otherwise
        if not verb:
            verb = 'POST' if postdict else 'GET'

        # By default don't retry POST or PUT. Retrying GET/DELETE is okay because they are idempotent.
        # In the future we could allow retrying PUT, so long as 'leavesQty' is not used (not idempotent),
        # or you could change the clOrdID (set {"clOrdID": "new", "origClOrdID": "old"}) so that an amend
        # can't erroneously be applied twice.
        if max_retries is None:
            max_retries = 0 if verb in ['POST', 'PUT'] else 3

        # Auth: API Key/Secret
        auth = APIKeyAuthWithExpires(self.apiKey, self.apiSecret)

        def exit_or_throw(e):
            if rethrow_errors:
                raise e
            else:
                exit(1)

        def retry():
            self.retries += 1
            if self.retries > max_retries:
                raise Exception("Max retries on %s (%s) hit, raising." % (path, json.dumps(postdict or '')))
            return self._curl_bitmex(path, query, postdict, timeout, verb, rethrow_errors, max_retries)

        # Make the request
        response = None
        try:
            self.logger.info("sending req to %s %s: %s" % (verb, url, json.dumps(postdict or query or '')))
            req = requests.Request(verb, url, json=postdict, auth=auth, params=query)
            prepped = self.session.prepare_request(req)
            response = self.session.send(prepped, timeout=timeout)
            # Make non-200s throw
            response.raise_for_status()

        except requests.exceptions.HTTPError as e:
            if response is None:
                raise e

            # 401 - Auth error. This is fatal.
            if response.status_code == 401:
                self.logger.error("API Key or Secret incorrect, please check and restart.")
                self.logger.error("Error: " + response.text)
                if postdict:
                    self.logger.error(postdict)
                # Always exit, even if rethrow_errors, because this is fatal
                exit(1)

            # 404, can be thrown if order canceled or does not exist.
            elif response.status_code == 404:
                if verb == 'DELETE':
                    self.logger.error("Order not found: %s" % postdict['orderID'])
                    return
                self.logger.error("Unable to contact the BitMEX API (404). " +
                                  "Request: %s \n %s" % (url, json.dumps(postdict)))
                exit_or_throw(e)

            # 429, ratelimit; cancel orders & wait until X-RateLimit-Reset
            elif response.status_code == 429:
                self.logger.error("Ratelimited on current request. Sleeping, then trying again. Try fewer " +
                                  "order pairs or contact support@bitmex.com to raise your limits. " +
                                  "Request: %s \n %s" % (url, json.dumps(postdict)))

                # Figure out how long we need to wait.
                ratelimit_reset = response.headers['X-RateLimit-Reset']
                to_sleep = int(ratelimit_reset) - int(time.time())
                reset_str = datetime.datetime.fromtimestamp(int(ratelimit_reset)).strftime('%X')

                # We're ratelimited, and we may be waiting for a long time. Cancel orders.
                self.logger.warning("Canceling all known orders in the meantime.")
                self.cancel([o['orderID'] for o in self.open_orders()])

                self.logger.error("Your ratelimit will reset at %s. Sleeping for %d seconds." % (reset_str, to_sleep))
                time.sleep(to_sleep)

                # Retry the request.
                return retry()

            # 503 - BitMEX temporary downtime, likely due to a deploy. Try again
            elif response.status_code == 503:
                self.logger.warning("Unable to contact the BitMEX API (503), retrying. " +
                                    "Request: %s \n %s" % (url, json.dumps(postdict)))
                time.sleep(3)
                return retry()

            elif response.status_code == 400:
                error = response.json()['error']
                message = error['message'].lower() if error else ''

                # Duplicate clOrdID: that's fine, probably a deploy, go get the order(s) and return it
                if 'duplicate clordid' in message:
                    orders = postdict['orders'] if 'orders' in postdict else postdict

                    IDs = json.dumps({'clOrdID': [order['clOrdID'] for order in orders]})
                    orderResults = self._curl_bitmex('/order', query={'filter': IDs}, verb='GET')

                    for i, order in enumerate(orderResults):
                        if (
                                order['orderQty'] != abs(postdict['orderQty']) or
                                order['side'] != ('Buy' if postdict['orderQty'] > 0 else 'Sell') or
                                order['price'] != postdict['price'] or
                                order['symbol'] != postdict['symbol']):
                            raise Exception('Attempted to recover from duplicate clOrdID, but order returned from API ' +
                                            'did not match POST.\nPOST data: %s\nReturned order: %s' % (
                                                json.dumps(orders[i]), json.dumps(order)))
                    # All good
                    return orderResults

                elif 'insufficient available balance' in message:
                    self.logger.error('Account out of funds. The message: %s' % error['message'])
                    exit_or_throw(Exception('Insufficient Funds'))


            # If we haven't returned or re-raised yet, we get here.
            self.logger.error("Unhandled Error: %s: %s" % (e, response.text))
            self.logger.error("Endpoint was: %s %s: %s" % (verb, path, json.dumps(postdict)))
            exit_or_throw(e)

        except requests.exceptions.Timeout as e:
            # Timeout, re-run this request
            self.logger.warning("Timed out on request: %s (%s), retrying..." % (path, json.dumps(postdict or '')))
            return retry()

        except requests.exceptions.ConnectionError as e:
            self.logger.warning("Unable to contact the BitMEX API (%s). Please check the URL. Retrying. " +
                                "Request: %s %s \n %s" % (e, url, json.dumps(postdict)))
            time.sleep(1)
            return retry()

        # Reset retry counter on success
        self.retries = 0

        return (response.json(), response.status_code)