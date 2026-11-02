from decimal import Decimal

import pytest

from deals.domain.mandate import Mandate, MandateViolation, check_payouts
from deals.domain.money import Money
from deals.domain.ports import WebhookEvent
from deals.domain.states import IllegalTransition
from deals.services.apply_webhook import apply_webhook
from deals.services.confirm_hold import confirm_hold
from deals.services.delivery_capture_void import capture, confirm_delivery
from deals.services.ledger import verify_ledger
from deals.services.mandate import set_mandate
from deals.services.open_deal import agree_terms, open_deal
from deals.services.open_hold import open_hold
from deals.services.send_payouts import PayoutsAlreadySent, item_key, send_payouts
from tests.fakes import FakePayments
from tests.test_services import held_deal

pytestmark = pytest.mark.django_db
TERMS = {"bundle": "standard", "total": "1000.00", "currency": "USD",
         "payouts": [{"sub_id": "ann", "amount": "200.00"}, {"sub_id": "bob", "amount": "100.00"}]}
OK = Mandate(True, {"ann": "ann@x.com", "bob": "bob@x.com"})


def captured(pay, mandate=OK):
    deal = agree_terms(open_deal("Kit", "c@example.com"), dict(TERMS))
    open_hold(deal, pay, "https://r", "https://c")
    confirm_hold(deal, pay)
    if mandate:
        set_mandate(deal, mandate)
    confirm_delivery(deal)
    return capture(deal, pay)


def hook(deal, sub, kind="SUCCEEDED", eid=None):
    res = {"payout_item_id": f"PI-{sub}", "payout_item": {"sender_item_id": item_key(deal, sub)}}
    return WebhookEvent(eid or f"EV-{sub}-{kind}", f"PAYMENT.PAYOUTS-ITEM.{kind}", f"PI-{sub}", res)


def test_payouts_go_to_approved_subs_and_close_out_on_webhooks():
    pay = FakePayments()
    deal = captured(pay)
    send_payouts(deal, pay)
    assert deal.state == "CAPTURED"  # not paid out until PayPal confirms
    sent = {i.receiver_email: i.amount for i in pay.payouts[0]}
    assert sent == {"ann@x.com": Money.of("200"), "bob@x.com": Money.of("100")}
    assert apply_webhook(hook(deal, "ann")) == "APPLIED"
    deal.refresh_from_db()
    assert deal.state == "CAPTURED"
    apply_webhook(hook(deal, "bob"))
    deal.refresh_from_db()
    assert deal.state == "PAID_OUT" and verify_ledger(deal) is None
    assert "PAYOUT_SENT" in deal.ledger.values_list("kind", flat=True)


def test_no_payout_before_capture_and_paypal_is_not_called():
    pay = FakePayments()
    deal = held_deal(pay)
    set_mandate(deal, OK)
    with pytest.raises(IllegalTransition):
        send_payouts(deal, pay)
    assert not [c for c in pay.calls if c[0] == "send_payout"]


def test_no_payout_without_mandate():
    pay = FakePayments()
    deal = captured(pay, mandate=None)
    with pytest.raises(MandateViolation):
        send_payouts(deal, pay)
    assert not pay.payouts


def test_unapproved_sub_blocks_the_whole_batch():
    pay = FakePayments()
    deal = captured(pay, Mandate(True, {"ann": "ann@x.com"}))
    with pytest.raises(MandateViolation):
        send_payouts(deal, pay)
    assert not pay.payouts


def test_payout_share_cap_is_enforced():
    low = Mandate(True, {"ann": "a@x.com", "bob": "b@x.com"}, Decimal("20"))
    with pytest.raises(MandateViolation):
        check_payouts(low, (("ann", Money.of(200)), ("bob", Money.of(100))), Money.of(1000))


def test_second_send_is_refused():
    pay = FakePayments()
    deal = captured(pay)
    send_payouts(deal, pay)
    with pytest.raises(PayoutsAlreadySent):
        send_payouts(deal, pay)
    assert len(pay.payouts) == 1


def test_repeated_webhook_is_applied_once():
    pay = FakePayments()
    deal = captured(pay)
    send_payouts(deal, pay)
    assert apply_webhook(hook(deal, "ann", eid="E1")) == "APPLIED"
    assert apply_webhook(hook(deal, "ann", eid="E1")) == "DUPLICATE"
    n = deal.ledger.filter(kind="PAYOUT_ITEM_SUCCEEDED").count()
    assert n == 1


def test_failed_item_is_recorded_and_deal_is_not_marked_paid():
    pay = FakePayments()
    deal = captured(pay)
    send_payouts(deal, pay)
    apply_webhook(hook(deal, "ann"))
    apply_webhook(hook(deal, "bob", "FAILED"))
    deal.refresh_from_db()
    assert deal.state == "CAPTURED"
    assert deal.payments.get(paypal_id=item_key(deal, "bob")).status == "FAILED"


def test_unrelated_and_unknown_events_do_nothing():
    ev = WebhookEvent("E9", "PAYMENT.CAPTURE.COMPLETED", "C1", {})
    assert apply_webhook(ev) == "IGNORED"
    stray = WebhookEvent("E10", "PAYMENT.PAYOUTS-ITEM.SUCCEEDED", "P", {"sender_item_id": "nope"})
    assert apply_webhook(stray) == "UNKNOWN_ITEM"


def test_payouts_switch_off_blocks_even_approved_subs():
    off = Mandate(False, {"ann": "a@x.com"})
    with pytest.raises(MandateViolation):
        check_payouts(off, (("ann", Money.of(200)),), Money.of(1000))


def test_refresh_finishes_the_payout_without_any_webhook():
    from deals.services.refresh_payouts import refresh_payouts
    pay = FakePayments()
    deal = captured(pay)
    send_payouts(deal, pay)
    assert refresh_payouts(deal, pay) == 2
    assert deal.state == "PAID_OUT"
    assert refresh_payouts(deal, pay) == 0  # a second refresh changes nothing
    assert verify_ledger(deal) is None


def test_refresh_keeps_waiting_while_paypal_says_pending():
    from deals.services.refresh_payouts import refresh_payouts
    pay = FakePayments()
    pay.payout_status = "PENDING"
    deal = captured(pay)
    send_payouts(deal, pay)
    assert refresh_payouts(deal, pay) == 0 and deal.state == "CAPTURED"


def test_refresh_records_a_failed_item_and_does_not_mark_paid():
    from deals.services.refresh_payouts import refresh_payouts
    pay = FakePayments()
    pay.payout_status = "FAILED"
    deal = captured(pay)
    send_payouts(deal, pay)
    refresh_payouts(deal, pay)
    assert deal.state == "CAPTURED"
    assert deal.payments.filter(kind="PAYOUT_ITEM", status="FAILED").count() == 2


def test_refresh_ignores_in_between_statuses_without_touching_the_ledger():
    from deals.services.refresh_payouts import refresh_payouts
    pay = FakePayments()
    pay.payout_status = "PROCESSING"
    deal = captured(pay)
    send_payouts(deal, pay)
    before = deal.ledger.count()
    refresh_payouts(deal, pay)
    assert deal.ledger.count() == before
    assert not deal.payments.filter(kind="PAYOUT_ITEM", status="PROCESSING").exists()


@pytest.mark.parametrize("bad", ["YOUR_ILLUSTRATOR_SANDBOX_EMAIL", "no-at-sign.com", "a@b", ""])
def test_mandate_rejects_receivers_that_are_not_emails(bad):
    with pytest.raises(MandateViolation):
        Mandate(True, {"ann": bad})
