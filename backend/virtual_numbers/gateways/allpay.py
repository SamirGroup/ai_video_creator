"""Integration boundary for allpay LIMITED (https://www.allpay.net/).

Gateway Plus documents hosted pages and HMAC, but not a public create/capture/
refund wire specification. Never substitute allpay.to/allpayx/Alipay APIs.
The methods below deliberately fail closed until the contracted specification
is supplied. This is an extension boundary, not a working native connector.
"""

from virtual_numbers.gateways import GatewayUnavailable


class AllpayGateway:
    def create_checkout(self, order):
        raise GatewayUnavailable(
            "allpay.net contract, transaction API and HMAC specification are required."
        )

    def verify_notification(self, body, headers):
        raise GatewayUnavailable(
            "allpay.net callback verification has not been configured."
        )

    def refund(self, order):
        raise GatewayUnavailable("allpay.net refund API has not been configured.")
