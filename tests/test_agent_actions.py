import json

import pytest

from agents.actor import ActionAgent, Choice
from agents.fake import FakeLLM
from agents.spend_guard import MemoryStore, SpendGuard
from deals.domain.mandate import Mandate
from deals.services.agent_act import agent_act
from deals.services.agent_run import agent_run
from deals.services.confirm_hold import confirm_hold
from deals.services.delivery_capture_void import confirm_delivery
from deals.services.ledger import verify_ledger
from deals.services.mandate import set_mandate
from deals.services.open_deal import agree_terms, open_deal
from deals.services.refresh_payouts import refresh_payouts
from tests.fakes import FakePayments

pytestmark = pytest.mark.django_db
TERMS = {"bundle": "standard", "total": "1000.00", "currency": "USD",
         "payouts": [{"sub_id": "ann", "amount": "200.00"}]}
FULL = Mandate(True, {"ann": "ann@x.com"}, allow_hold=True, allow_capture=True, allow_void=True)


def agreed(mandate=FULL):
    deal = agree_terms(open_deal("Kit", "c@example.com"), dict(TERMS))
    return set_mandate(deal, mandate) if mandate else deal


def actor(replies=()):
    return ActionAgent(FakeLLM(replies), SpendGuard(MemoryStore()))


def acts(deal):
    return [e.payload for e in deal.ledger.filter(kind="AGENT_ACTION").order_by("seq")]


def calls(pay, name):
    return [c for c in pay.calls if c[0] == name]


def test_the_agent_runs_the_deal_and_the_humans_only_do_their_three_steps():
    pay, a = FakePayments(), actor()
    deal = agreed()
    agent_run(deal, pay, a)  # opens the hold, then must wait for the client
    assert deal.state == "HOLD_PENDING" and acts(deal)[0]["order_id"] == "ORDER-1"
    confirm_hold(deal, pay)  # human: the client approved on PayPal
    assert agent_run(deal, pay, a) == [] and not calls(pay, "capture")
    confirm_delivery(deal)  # human: the client confirmed delivery
    agent_run(deal, pay, a)  # captures, then pays the sub-contractor
    assert [x["tool"] for x in acts(deal)] == ["open_hold", "capture", "send_payouts"]
    assert acts(deal)[1]["capture_id"] == "CAP-1" and acts(deal)[2]["batch_id"] == "BATCH-1"
    assert refresh_payouts(deal, pay) == 1 and deal.state == "PAID_OUT"
    assert verify_ledger(deal) is None


def test_model_choices_are_recorded_with_their_reason():
    pay = FakePayments()
    deal = agreed()
    a = actor([json.dumps({"tool": "open_hold", "reason": "terms are agreed"})])
    agent_run(deal, pay, a)
    assert acts(deal)[0]["source"] == "model" and acts(deal)[0]["why"] == "terms are agreed"


def test_without_permission_the_agent_does_nothing_and_paypal_is_not_called():
    pay, deal = FakePayments(), agreed(Mandate(True, {"ann": "ann@x.com"}))
    assert agent_run(deal, pay, actor()) == [] and not pay.calls
    assert deal.state == "AGREED"


def test_capture_is_refused_before_delivery_and_the_refusal_is_logged():
    pay = FakePayments()
    deal = agreed()
    agent_run(deal, pay, actor())
    confirm_hold(deal, pay)
    res = agent_act(deal, pay, "capture")
    assert not res.ok and not calls(pay, "capture")
    assert acts(deal)[-1]["ok"] is False and "CAPTURE_DONE" in acts(deal)[-1]["error"]


def test_a_missing_permission_is_refused_even_if_called_directly():
    pay = FakePayments()
    deal = agreed(Mandate(True, {"ann": "ann@x.com"}, allow_hold=True))
    agent_run(deal, pay, actor())
    confirm_hold(deal, pay)
    confirm_delivery(deal)
    res = agent_act(deal, pay, "capture")
    assert not res.ok and "mandate" in res.detail and not calls(pay, "capture")


def test_unknown_tools_are_refused():
    res = agent_act(agreed(), FakePayments(), "refund_everyone")
    assert not res.ok


def test_changed_terms_make_the_agent_void_instead_of_capture():
    pay = FakePayments()
    deal = agreed()
    agent_run(deal, pay, actor())
    confirm_hold(deal, pay)
    confirm_delivery(deal)
    agent_run(deal, pay, actor([json.dumps({"tool": "capture"})]), terms_changed=True)
    assert deal.state == "VOIDED" and not calls(pay, "capture") and calls(pay, "void")


def test_a_failed_payout_is_logged_and_stops_the_agent_after_capture():
    pay = FakePayments()
    deal = agreed(Mandate(True, {}, allow_hold=True, allow_capture=True))  # no approved subs
    agent_run(deal, pay, actor())
    confirm_hold(deal, pay)
    confirm_delivery(deal)
    results = agent_run(deal, pay, actor())
    assert [(r.tool, r.ok) for r in results] == [("capture", True), ("send_payouts", False)]
    assert deal.state == "CAPTURED" and not pay.payouts and acts(deal)[-1]["ok"] is False


class Rogue:
    def choose(self, *args):
        return Choice("capture", "trust me", "model")


def test_an_actor_that_ignores_the_menu_is_stopped_and_recorded():
    pay, deal = FakePayments(), agreed()
    agent_run(deal, pay, actor())
    assert agent_run(deal, pay, Rogue()) == []
    assert acts(deal)[-1]["error"] == "not on the menu" and not calls(pay, "capture")


def test_the_state_is_checked_before_the_mandate():
    pay = FakePayments()
    deal = agreed(Mandate(True, {"ann": "ann@x.com"}, allow_hold=True))  # may not capture
    agent_run(deal, pay, actor())
    confirm_hold(deal, pay)  # still HOLD_ACTIVE, so both rules say no
    assert "not allowed in state" in agent_act(deal, pay, "capture").detail
