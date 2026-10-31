from io import StringIO

import pytest
from django.core.management import call_command

from deals.domain.money import Money
from deals.services.delivery_capture_void import capture, confirm_delivery
from deals.services.seal import anchor_ok, build_receipt
from render.sealed_receipt import receipt_html, receipt_text
from tests.fakes import FakePayments
from tests.helpers import forge_entry
from tests.test_services import held_deal

pytestmark = pytest.mark.django_db


def captured_deal():
    pay = FakePayments()
    deal = held_deal(pay)
    confirm_delivery(deal)
    capture(deal, pay)
    return deal, pay


def test_receipt_data_for_a_captured_deal():
    deal, pay = captured_deal()
    d = build_receipt(deal, anchor_ok(deal, pay))
    assert d["intact"] and d["anchor"] is True and d["broken_seq"] is None
    assert d["paypal"] == {"order_id": "ORDER-1", "authorization_id": "AUTH-1",
                           "capture_id": "CAP-1"}
    assert len(d["entries"]) == 6 and d["head_hash"] == d["entries"][-1]["hash"]


def test_text_receipt_shows_hash_ids_and_verdict():
    deal, _ = captured_deal()
    text = receipt_text(build_receipt(deal))
    assert deal.terms_hash in text and "CAP-1" in text and "ledger: intact" in text
    assert "anchored in PayPal: not checked" in text


def test_tampering_is_reported_in_the_receipt():
    deal, _ = captured_deal()
    forge_entry(deal, 3)
    d = build_receipt(deal)
    assert not d["intact"] and d["broken_seq"] == 3
    assert "BROKEN at entry 3" in receipt_text(d)


def test_html_receipt_escapes_untrusted_text():
    deal, _ = captured_deal()
    d = build_receipt(deal)
    d["title"] = "<script>alert(1)</script>"
    html = receipt_html(d)
    assert "<script>" not in html and "&lt;script&gt;" in html


def test_anchor_mismatch_is_flagged():
    deal, _ = captured_deal()
    other = FakePayments(tamper_custom_id=True)
    other._hold = (Money.of(deal.total_amount, deal.currency), deal.terms_hash)
    assert anchor_ok(deal, other) is False


def test_tamper_demo_detects_and_leaves_data_unchanged():
    deal, _ = captured_deal()
    out = StringIO()
    call_command("tamper_demo", str(deal.pk), stdout=out)
    text = out.getvalue()
    assert "BROKEN at entry 2" in text and text.strip().endswith("intact")
    assert build_receipt(deal)["intact"]


def test_receipt_command_prints_newest_deal():
    deal, _ = captured_deal()
    out = StringIO()
    call_command("receipt", stdout=out)
    assert str(deal.pk) in out.getvalue()
