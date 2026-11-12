"""The deal page panels, the capture lock and settling a deal that owes no sub-contractor."""
from decimal import Decimal
from types import SimpleNamespace

import pytest

from agents.freelancer import FreelancerAgent
from agents.llm import NoModel
from agents.spend_guard import MemoryStore, SpendGuard
from deals.domain.states import IllegalTransition
from deals.models import Deal, PaymentRecord
from deals.services.deal_view import build_deal_view
from deals.services.delivery_capture_void import capture
from deals.services.negotiate_round import play_round, start_negotiation
from deals.services.open_deal import open_deal
from deals.services.send_payouts import settle_without_payouts
from engine.demo_card import demo_card


def _deal(accept):
    deal = open_deal("Brand identity", "c@example.com")
    card = demo_card()
    start_negotiation(deal, card, "standard")
    if accept:
        freelancer = FreelancerAgent(NoModel(), SpendGuard(MemoryStore()))
        play_round(deal, card, "standard", freelancer, "ACCEPT", None, "ok")
        deal.refresh_from_db()
    return deal


@pytest.fixture
def negotiating(db):
    return _deal(accept=False)


@pytest.fixture
def agreed(db):
    return _deal(accept=True)


class FakePayments:
    def __init__(self):
        self.captures = 0

    def capture(self, *args):
        self.captures += 1
        return SimpleNamespace(capture_id="CAP1", status="COMPLETED")


def test_second_capture_is_refused_even_from_a_stale_copy(agreed):
    Deal.objects.filter(pk=agreed.pk).update(state="DELIVERED", auth_id="AUTH1")
    stale = Deal.objects.get(pk=agreed.pk)
    payments = FakePayments()
    capture(Deal.objects.get(pk=agreed.pk), payments)
    with pytest.raises(IllegalTransition):
        capture(stale, payments)  # the lock re-reads the row, so the stale copy is refused
    assert payments.captures == 1
    assert PaymentRecord.objects.filter(deal=agreed, kind="CAPTURE").count() == 1


def test_captured_deal_with_no_payouts_finishes(agreed):
    agreed.terms = {**agreed.terms, "payouts": []}
    agreed.state = "CAPTURED"
    agreed.save()
    assert settle_without_payouts(agreed) is True
    agreed.refresh_from_db()
    assert agreed.state == "PAID_OUT"
    assert settle_without_payouts(agreed) is False  # nothing left to do
    view = build_deal_view(agreed.pk)
    assert view["paypal"]["headline"] == "Completed"
    assert view["paypal"]["steps"][-1]["done"] is True
    assert next(s for s in view["timeline"] if s["label"] == "Payouts confirmed")["done"]


def test_captured_deal_with_payouts_keeps_waiting(agreed):
    agreed.terms = {**agreed.terms, "payouts": [{"sub_id": "s1", "amount": "100.00"}]}
    agreed.state = "CAPTURED"
    agreed.save()
    assert settle_without_payouts(agreed) is False
    agreed.refresh_from_db()
    assert agreed.state == "CAPTURED"


def test_panels_for_an_agreed_deal(agreed):
    view = build_deal_view(agreed.pk)
    assert view["paypal"]["headline"] == "Ready to request authorization"
    assert not any(s["done"] for s in view["paypal"]["steps"])
    assert view["proposal"]["status"] == "Agreed"
    assert Decimal(view["proposal"]["price"].split()[0]) == Decimal("1800.00")
    assert view["parties"]["provider"] == "The freelancer’s agent"
    assert view["activity"][0]["label"] == "Deal opened"


def test_paypal_card_waits_for_agreement_and_chat_comes_first(client, negotiating):
    page = client.get(f"/deals/{negotiating.pk}/").content.decode()
    assert "PayPal payment" not in page
    assert page.index("h-talk") < page.index("h-glance")
    assert "data-say" in page


def test_paypal_card_shows_once_terms_are_agreed(client, agreed):
    page = client.get(f"/deals/{agreed.pk}/").content.decode()
    assert "PayPal payment" in page and "Ready to request authorization" in page
