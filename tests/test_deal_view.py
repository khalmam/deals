import uuid

import pytest

from deals.services.deal_view import DealNotFound, build_deal_view
from deals.services.ledger import append
from deals.services.open_deal import agree_terms, open_deal
from tests.helpers import forge_entry

TERMS = {
    "bundle": "brand", "bundle_name": "Brand site", "total": "1740.00", "currency": "USD",
    "list_price": "1800.00", "line_items": [{"name": "Design", "amount": "1800.00"}],
    "payouts": [{"sub_id": "dev", "amount": "600.00"}], "freelancer_net": "1140.00",
    "net_days": "7", "late_fee_pct": "5",
}


@pytest.fixture
def deal(db):
    d = open_deal("Brand site", "client@example.com")
    append(d, "OFFER_MADE", {"by": "freelancer", "price": "1800.00", "currency": "USD",
                             "source": "rate_card", "message": "Opening ask"})
    append(d, "COUNTER_MADE", {"by": "client", "price": "1500.00", "currency": "USD",
                               "message": "Can you do 1500?"})
    agree_terms(d, TERMS)
    append(d, "AGENT_ACTION", {"tool": "open_hold", "ok": True, "why": "terms agreed",
                               "source": "model"})
    return d


def test_view_is_plain_data(deal):
    v = build_deal_view(deal.pk)
    assert v["ledger"][0]["kind"] == "DEAL_OPENED"
    assert [m["who"] for m in v["transcript"]] == ["Freelancer", "Client"]
    assert v["terms"]["bundle"] == "Brand site"
    assert v["actions"][0]["decided_by"] == "Model"
    assert v["verified"] is None


def test_timeline_marks_what_happened(deal):
    steps = {s["label"]: s["done"] for s in build_deal_view(deal.pk)["timeline"]}
    assert steps["Terms agreed"] and not steps["Payment captured"]


def test_verify_reports_intact(deal):
    assert build_deal_view(deal.pk, verify=True)["verified"]["intact"] is True


def test_unknown_deal(db):
    with pytest.raises(DealNotFound):
        build_deal_view(uuid.uuid4())


def test_page_renders(client, deal):
    r = client.get(f"/deals/{deal.pk}/")
    assert r.status_code == 200
    assert b"Brand site" in r.content and b"Verify ledger" in r.content


def test_verify_button_result(client, deal):
    assert b"Intact" in client.get(f"/deals/{deal.pk}/?verify=1").content


def test_tampering_is_shown(client, deal):
    forged = {"by": "freelancer", "price": "1.00"}
    forge_entry(deal, 2, forged)
    assert b"Broken at entry" in client.get(f"/deals/{deal.pk}/?verify=1").content


def test_missing_deal_is_404(client, db):
    assert client.get(f"/deals/{uuid.uuid4()}/").status_code == 404


def test_page_verifies_on_every_load(client, deal):
    page = client.get(f"/deals/{deal.pk}/").content.decode()
    assert "Intact." in page and "entries verified" in page
