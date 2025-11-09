#https://github.com/BitMEX/sample-market-maker/blob/master/market_maker/auth/APIKeyAuthWithExpires.py
from requests.auth import AuthBase
import time
#from market_maker.auth.APIKeyAuth import generate_signature
import hashlib
import hmac
from urllib.parse import urlparse
#^https://github.com/BitMEX/sample-market-maker/blob/master/market_maker/auth/APIKeyAuth.py#L55


def generate_signature(secret, verb, url, nonce, data):
    """Generate a request signature compatible with BitMEX."""
    # Parse the url so we can remove the base and extract just the path.
    parsedURL = urlparse(url)
    path = parsedURL.path
    if parsedURL.query:
        path = path + '?' + parsedURL.query

    if isinstance(data, (bytes, bytearray)):
        data = data.decode('utf8')

    # print "Computing HMAC: %s" % verb + path + str(nonce) + data
    message = verb + path + str(nonce) + data

    signature = hmac.new(bytes(secret, 'utf8'), bytes(message, 'utf8'), digestmod=hashlib.sha256).hexdigest()
    return signature


class APIKeyAuthWithExpires(AuthBase):

    """Attaches API Key Authentication to the given Request object. This implementation uses `expires`."""

    def __init__(self, apiKey, apiSecret):
        """Init with Key & Secret."""
        self.apiKey = apiKey
        self.apiSecret = apiSecret

    def __call__(self, r):
        """
        Called when forming a request - generates api key headers. This call uses `expires` instead of nonce.

        This way it will not collide with other processes using the same API Key if requests arrive out of order.
        For more details, see https://www.bitmex.com/app/apiKeys
        """
        # modify and return the request
        expires = int(round(time.time()) + 5)  # 5s grace period in case of clock skew
        r.headers['api-expires'] = str(expires)
        r.headers['api-key'] = self.apiKey
        r.headers['api-signature'] = generate_signature(self.apiSecret, r.method, r.url, expires, r.body or '')

        return r
