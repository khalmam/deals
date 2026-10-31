import json

import httpx

from deals.domain.money import Money
from deals.domain.ports import PayoutItem
from paypal.client import PayPalClient, PayPalConfig
from paypal.payments import PayPalPayments


def adapter(routes, log):
    def handler(request):
        if request.url.path == "/v1/oauth2/token":
            return httpx.Response(200, json={"access_token": "t", "expires_in": 3600})
        body = json.loads(request.content) if request.content else None
        log.append((request.method, request.url.path, body))
        return httpx.Response(200, json=routes[request.url.path])
    transport = httpx.MockTransport(handler)
    return PayPalPayments(PayPalClient(PayPalConfig("i", "s"), transport=transport))


def test_create_hold_anchors_terms_hash_and_returns_approval_link():
    log = []
    p = adapter({"/v2/checkout/orders": {"id": "O1", "links": [
        {"rel": "self", "href": "x"}, {"rel": "payer-action", "href": "https://pay/O1"}]}}, log)
    hold = p.create_hold("deal1", Money.of("50"), "abc123", "https://r", "https://c")
    assert (hold.order_id, hold.approve_url) == ("O1", "https://pay/O1")
    body = log[0][2]
    assert body["intent"] == "AUTHORIZE"
    assert body["purchase_units"][0]["custom_id"] == "abc123"
    assert body["purchase_units"][0]["amount"] == {"currency_code": "USD", "value": "50.00"}


def test_authorize_parses_authorization():
    log = []
    p = adapter({"/v2/checkout/orders/O1/authorize": {"purchase_units": [{"payments": {
        "authorizations": [{"id": "A1", "expiration_time": "2026-11-24T00:00:00Z",
                            "amount": {"currency_code": "USD", "value": "50.00"}}]}}]}}, log)
    a = p.authorize("deal1", "O1")
    assert a.auth_id == "A1" and a.expires_at.startswith("2026-11-24")


def test_partial_capture_sends_amount_and_final_flag():
    log = []
    route = {"/v2/payments/authorizations/A1/capture": {"id": "C1", "status": "COMPLETED"}}
    p = adapter(route, log)
    c = p.capture("deal1", "A1", Money.of("20"), final=False, step="1")
    assert c.capture_id == "C1"
    expected = {"amount": {"currency_code": "USD", "value": "20.00"}, "final_capture": False}
    assert log[0][2] == expected


def test_void_posts_json_body():
    log = []
    p = adapter({"/v2/payments/authorizations/A1/void": {}}, log)
    p.void("deal1", "A1")
    assert log[0][2] == {}


def test_payout_items_use_currency_field():
    log = []
    p = adapter({"/v1/payments/payouts": {"batch_header": {
        "payout_batch_id": "B1", "batch_status": "PENDING"}}}, log)
    r = p.send_payout("batch-1", [PayoutItem("sub@example.com", Money.of("4"), "item-1", "n")])
    assert r.batch_id == "B1"
    item = log[0][2]["items"][0]
    assert item["amount"] == {"currency": "USD", "value": "4.00"}
    assert log[0][2]["sender_batch_header"]["sender_batch_id"] == "batch-1"


def test_get_payout_returns_item_statuses():
    log = []
    p = adapter({"/v1/payments/payouts/B1": {"batch_header": {"batch_status": "SUCCESS"},
                                              "items": [{"payout_item_id": "I1",
                                                         "transaction_status": "SUCCESS"}]}}, log)
    r = p.get_payout("B1")
    assert r.status == "SUCCESS" and r.items == (("I1", "SUCCESS"),)
