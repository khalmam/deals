import json

import pytest
from django.test import Client

import web.views
from deals.models import WebhookEvent
from deals.services.ledger import verify_ledger
from deals.services.send_payouts import send_payouts
from paypal.webhooks import WebhookGateway, parse_event
from tests.fakes import FakePayments
from tests.test_payouts import captured, hook

pytestmark = pytest.mark.django_db
URL = "/webhooks/paypal/"


class Gateway:
    def __init__(self, ok=True):
        self.ok, self.seen = ok, []

    def verify(self, headers, raw):
        self.seen.append((dict(headers), raw))
        return self.ok

    def parse(self, raw):
        return parse_event(raw)


def raw_event(deal, sub, kind="SUCCEEDED", eid="WH-1"):
    ev = hook(deal, sub, kind, eid)
    return {"id": ev.event_id, "event_type": ev.event_type, "resource": ev.resource}


def post(body, gw, monkeypatch, **headers):
    monkeypatch.setattr(web.views, "get_gateway", lambda: gw)
    data = body if isinstance(body, (str, bytes)) else json.dumps(body)
    return Client(raise_request_exception=False).post(URL, data, content_type="application/json",
                                                      **headers)


def sent_deal():
    pay = FakePayments()
    deal = captured(pay)
    send_payouts(deal, pay)
    return deal


def test_a_signed_event_is_applied_and_its_raw_shape_is_kept(monkeypatch):
    deal, gw = sent_deal(), Gateway()
    ev = raw_event(deal, "ann")
    r = post(ev, gw, monkeypatch, HTTP_PAYPAL_TRANSMISSION_ID="T1")
    assert r.status_code == 200 and r.json() == {"result": "APPLIED"}
    assert gw.seen[0][0]["Paypal-Transmission-Id"] == "T1" and gw.seen[0][1] == ev
    row = WebhookEvent.objects.get(event_id="WH-1")
    assert row.payload == ev and row.applied
    assert deal.ledger.filter(kind="PAYOUT_ITEM_SUCCEEDED").count() == 1
    assert verify_ledger(deal) is None


def test_a_bad_signature_is_a_400_and_changes_nothing(monkeypatch):
    deal = sent_deal()
    r = post(raw_event(deal, "ann"), Gateway(ok=False), monkeypatch)
    assert r.status_code == 400 and not WebhookEvent.objects.exists()
    assert not deal.ledger.filter(kind="PAYOUT_ITEM_SUCCEEDED").exists()


@pytest.mark.parametrize("body", ["not json", "[1, 2]", "42"])
def test_junk_bodies_are_a_400(body, monkeypatch):
    assert post(body, Gateway(), monkeypatch).status_code == 400


def test_a_signed_body_without_id_or_type_is_a_400(monkeypatch):
    assert post({"resource": {}}, Gateway(), monkeypatch).status_code == 400
    assert not WebhookEvent.objects.exists()


def test_a_repeated_delivery_is_a_200_and_applied_once(monkeypatch):
    deal, gw = sent_deal(), Gateway()
    ev = raw_event(deal, "ann")
    assert post(ev, gw, monkeypatch).json() == {"result": "APPLIED"}
    again = post(ev, gw, monkeypatch)
    assert again.status_code == 200 and again.json() == {"result": "DUPLICATE"}
    assert deal.ledger.filter(kind="PAYOUT_ITEM_SUCCEEDED").count() == 1


def test_events_we_do_not_handle_are_a_200_with_their_raw_shape_kept(monkeypatch):
    ev = {"id": "WH-9", "event_type": "PAYMENT.CAPTURE.COMPLETED", "resource": {"id": "C1"}}
    r = post(ev, Gateway(), monkeypatch)
    assert r.status_code == 200 and r.json() == {"result": "IGNORED"}
    assert WebhookEvent.objects.get(event_id="WH-9").payload == ev


def test_only_post_is_allowed(monkeypatch):
    monkeypatch.setattr(web.views, "get_gateway", lambda: Gateway())
    assert Client().get(URL).status_code == 405


def test_a_paypal_outage_while_verifying_is_a_5xx_so_paypal_retries(monkeypatch):
    class Down(Gateway):
        def verify(self, headers, raw):
            raise RuntimeError("PayPal is down")

    r = post({"id": "WH-2", "event_type": "X", "resource": {}}, Down(), monkeypatch)
    assert r.status_code == 500 and not WebhookEvent.objects.exists()


def test_an_event_that_failed_half_way_is_applied_when_paypal_retries(monkeypatch):
    import deals.services.apply_webhook as aw

    deal, gw = sent_deal(), Gateway()
    ev, real = raw_event(deal, "ann"), aw.record_item_status
    monkeypatch.setattr(aw, "record_item_status", lambda *a, **k: 1 / 0)
    assert post(ev, gw, monkeypatch).status_code == 500
    assert not WebhookEvent.objects.get(event_id="WH-1").applied
    monkeypatch.setattr(aw, "record_item_status", real)
    assert post(ev, gw, monkeypatch).json() == {"result": "APPLIED"}
    assert deal.ledger.filter(kind="PAYOUT_ITEM_SUCCEEDED").count() == 1


def test_parse_event_reads_the_payout_item_id():
    ev = parse_event({"id": "W", "event_type": "T", "resource": {"payout_item_id": "PI-1"}})
    assert ev.resource_id == "PI-1"
    assert parse_event({"id": "W", "event_type": "T", "resource": {"id": "C1"}}).resource_id == "C1"


def test_the_gateway_refuses_to_exist_without_a_webhook_id():
    with pytest.raises(ValueError, match="PAYPAL_WEBHOOK_ID"):
        WebhookGateway(object(), "")
