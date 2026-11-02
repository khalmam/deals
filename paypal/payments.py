"""Hold, capture, void, refund and payouts. Request shapes match what the Oct 26 spike proved."""
from deals.domain.money import Money
from deals.domain.ports import Authorization, Capture, HoldRequest, PayoutResult

from .client import PayPalClient, PayPalError, request_key


def _money(d):
    return Money.of(d["value"], d.get("currency_code") or d.get("currency", "USD"))


def _auth(d, custom_id=None):
    return Authorization(d["id"], d.get("expiration_time", ""), _money(d["amount"]),
                         d.get("custom_id") or custom_id)


class PayPalPayments:
    def __init__(self, client: PayPalClient):
        self._c = client

    def create_hold(self, deal_ref, amount, terms_hash, return_url, cancel_url):
        body = {
            "intent": "AUTHORIZE",
            "purchase_units": [{"amount": amount.to_paypal(), "custom_id": terms_hash}],
            "payment_source": {"paypal": {"experience_context": {
                "return_url": return_url, "cancel_url": cancel_url}}},
        }
        d = self._c.request("POST", "/v2/checkout/orders", body, request_key(deal_ref, "hold"))
        links = {x["rel"]: x["href"] for x in d.get("links", [])}
        url = links.get("payer-action") or links.get("approve")
        if not url:
            raise PayPalError(502, "NO_APPROVAL_LINK", "PayPal returned no approval link")
        return HoldRequest(d["id"], url)

    def authorize(self, deal_ref, order_id):
        d = self._c.request("POST", f"/v2/checkout/orders/{order_id}/authorize",
                            request_id=request_key(deal_ref, "authorize"))
        pu = d["purchase_units"][0]
        return _auth(pu["payments"]["authorizations"][0], pu.get("custom_id"))

    def get_authorization(self, auth_id):
        return _auth(self._c.request("GET", f"/v2/payments/authorizations/{auth_id}"))

    def capture(self, deal_ref, auth_id, amount, final, step):
        body = {"amount": amount.to_paypal(), "final_capture": bool(final)}
        d = self._c.request("POST", f"/v2/payments/authorizations/{auth_id}/capture", body,
                            request_key(deal_ref, "capture", step))
        return Capture(d["id"], d.get("status", ""), amount)

    def void(self, deal_ref, auth_id):
        self._c.request("POST", f"/v2/payments/authorizations/{auth_id}/void",
                        request_id=request_key(deal_ref, "void"))

    def refund(self, deal_ref, capture_id, amount, step):
        d = self._c.request("POST", f"/v2/payments/captures/{capture_id}/refund",
                            {"amount": amount.to_paypal()},
                            request_key(deal_ref, "refund", step))
        return d["id"]

    def send_payout(self, batch_key, items):
        body = {
            "sender_batch_header": {"sender_batch_id": batch_key,
                                    "email_subject": "Payment from Deals"},
            "items": [{"recipient_type": "EMAIL", "receiver": i.receiver_email,
                       "sender_item_id": i.item_key, "amount": i.amount.to_payout(),
                       "note": i.note} for i in items],
        }
        d = self._c.request("POST", "/v1/payments/payouts", body, batch_key)
        h = d["batch_header"]
        return PayoutResult(h["payout_batch_id"], h["batch_status"])

    def get_payout(self, batch_id):
        d = self._c.request("GET", f"/v1/payments/payouts/{batch_id}")
        items = tuple((i["payout_item_id"], i["transaction_status"],
                       (i.get("payout_item") or {}).get("sender_item_id", ""))
                      for i in d.get("items", []))
        return PayoutResult(batch_id, d["batch_header"]["batch_status"], items)
