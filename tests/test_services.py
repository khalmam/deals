import pytest
from django.db import connection

from deals.domain.states import IllegalTransition
from deals.models import LedgerEntry, PaymentRecord
from deals.services.confirm_hold import TermsMismatch, confirm_hold
from deals.services.delivery_capture_void import capture, confirm_delivery, void
from deals.services.ledger import verify_ledger
from deals.services.open_deal import agree_terms, open_deal
from deals.services.open_hold import open_hold
from tests.fakes import FakePayments

pytestmark = pytest.mark.django_db
TERMS = {"bundle": "standard", "total": "1800.00", "currency": "USD"}


def agreed_deal():
    deal = open_deal("Brand kit", "client@example.com")
    return agree_terms(deal, dict(TERMS))


def held_deal(pay):
    deal = agreed_deal()
    open_hold(deal, pay, "https://r", "https://c")
    return confirm_hold(deal, pay)


def kinds(deal):
    return list(deal.ledger.order_by("seq").values_list("kind", flat=True))


def test_happy_path_ends_captured_with_intact_ledger():
    pay = FakePayments()
    deal = held_deal(pay)
    confirm_delivery(deal)
    capture(deal, pay)
    assert deal.state == "CAPTURED"
    assert kinds(deal) == ["DEAL_OPENED", "TERMS_AGREED", "HOLD_REQUESTED", "HOLD_AUTHORIZED",
                           "DELIVERY_CONFIRMED", "CAPTURE_COMPLETED"]
    assert verify_ledger(deal) is None
    assert PaymentRecord.objects.get(deal=deal).paypal_id == "CAP-1"


def test_cannot_capture_before_delivery_and_paypal_is_not_called():
    pay = FakePayments()
    deal = held_deal(pay)
    with pytest.raises(IllegalTransition):
        capture(deal, pay)
    assert not [c for c in pay.calls if c[0] == "capture"]


def test_double_capture_is_refused():
    pay = FakePayments()
    deal = held_deal(pay)
    confirm_delivery(deal)
    capture(deal, pay)
    with pytest.raises(IllegalTransition):
        capture(deal, pay)
    assert len([c for c in pay.calls if c[0] == "capture"]) == 1


def test_void_releases_hold_and_blocks_capture():
    pay = FakePayments()
    deal = held_deal(pay)
    void(deal, pay)
    assert deal.state == "VOIDED" and ("void", str(deal.pk)) in pay.calls
    with pytest.raises(IllegalTransition):
        capture(deal, pay)


def test_cannot_void_after_capture():
    pay = FakePayments()
    deal = held_deal(pay)
    confirm_delivery(deal)
    capture(deal, pay)
    with pytest.raises(IllegalTransition):
        void(deal, pay)


def test_hold_with_wrong_terms_hash_is_released_and_not_activated():
    pay = FakePayments(tamper_custom_id=True)
    deal = agreed_deal()
    open_hold(deal, pay, "https://r", "https://c")
    with pytest.raises(TermsMismatch):
        confirm_hold(deal, pay)
    assert deal.state == "HOLD_PENDING"
    assert ("void", str(deal.pk)) in pay.calls


def test_every_paypal_call_is_keyed_by_the_deal_id():
    pay = FakePayments()
    deal = held_deal(pay)
    confirm_delivery(deal)
    capture(deal, pay)
    assert pay.calls and all(c[1] == str(deal.pk) for c in pay.calls)


def test_floats_in_terms_are_rejected():
    deal = open_deal("x", "c@example.com")
    with pytest.raises(ValueError):
        agree_terms(deal, {"total": "10.00", "currency": "USD", "extra": 1.5})


def test_editing_a_ledger_row_is_detected():
    """Models an attacker with admin rights who disables the trigger, then edits history."""
    pay = FakePayments()
    deal = held_deal(pay)
    if connection.vendor == "postgresql":
        with connection.cursor() as c:  # rolled back with the test transaction
            c.execute("SET CONSTRAINTS ALL IMMEDIATE")  # flush deferred FK checks first
            c.execute("ALTER TABLE deals_ledgerentry DISABLE TRIGGER USER")
    row = LedgerEntry.objects.get(deal=deal, seq=2)
    LedgerEntry.objects.filter(pk=row.pk).update(payload={"terms_hash": "forged"})
    assert verify_ledger(deal) == 1  # zero-based index of seq 2


def test_postgres_trigger_blocks_ledger_edits():
    if connection.vendor != "postgresql":
        pytest.skip("trigger test runs only against Postgres")
    from django.db import DatabaseError, transaction
    deal = held_deal(FakePayments())
    with pytest.raises(DatabaseError), transaction.atomic():
        LedgerEntry.objects.filter(deal=deal).update(kind="OFFER_MADE")
