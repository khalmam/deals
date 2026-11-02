import json
from decimal import Decimal

import pytest

from agents.client_sim import Persona, ScriptedClient
from agents.fake import FakeLLM
from agents.freelancer import FreelancerAgent
from agents.llm import NoModel
from agents.spend_guard import MemoryStore, SpendGuard
from deals.domain.money import Money
from deals.services.ledger import verify_ledger
from deals.services.negotiate import negotiate
from deals.services.open_deal import open_deal
from engine.demo_card import demo_card

pytestmark = pytest.mark.django_db
CARD = demo_card()


def freelancer(llm, **guard):
    return FreelancerAgent(llm, SpendGuard(MemoryStore(), **guard))


def client(ceiling, target=1200, **kw):
    return ScriptedClient(Persona("c", Money.of(target), Money.of(ceiling), seed=3, **kw))


def run(llm, ceiling=1650, **kw):
    deal = open_deal("Brand kit", "client@example.com")
    out = negotiate(deal, CARD, "standard", freelancer(llm), client(ceiling, **kw))
    return deal, out


def offers(deal):
    return [e.payload for e in deal.ledger.filter(kind="OFFER_MADE").order_by("seq")]


def offer(price, message="Glad to work with you."):
    return json.dumps({"action": "OFFER", "price": price, "message": message})


def test_engine_only_negotiation_reaches_an_agreement_inside_the_band():
    deal, out = run(NoModel())
    assert out.status == "AGREED" and out.price == Money.of(1620)
    assert deal.state == "AGREED" and deal.total_amount == out.price.amount
    assert deal.terms["freelancer_net"] and deal.terms["bundle"] == "standard"
    assert verify_ledger(deal) is None


def test_ledger_tells_the_story_in_order():
    deal, _ = run(NoModel())
    kinds = list(deal.ledger.order_by("seq").values_list("kind", flat=True))
    assert kinds[:3] == ["DEAL_OPENED", "OFFER_MADE", "COUNTER_MADE"]
    assert kinds[-1] == "TERMS_AGREED" and kinds.count("COUNTER_MADE") == 4


def test_model_may_hold_its_price_above_the_schedule():
    deal, out = run(FakeLLM([offer("1760.00"), offer("1700.00")]))
    sources = [(o["source"], o["price"]) for o in offers(deal)]
    assert sources[1] == ("model", "1760.00") and sources[2] == ("model", "1700.00")
    assert out.status == "AGREED" and out.price >= Money.of(1500)


def test_model_cannot_concede_faster_than_the_schedule():
    deal, _ = run(FakeLLM([offer("1000.00"), offer("1.00"), offer("1500.00")]))
    for o in offers(deal)[1:]:
        assert o["source"] == "engine" and "PRICE_OUTSIDE_WINDOW" in o["notes"]
    assert [o["price"] for o in offers(deal)] == ["1800.00", "1740.00", "1680.00", "1620.00"]


def test_model_cannot_raise_its_own_ask():
    deal, _ = run(FakeLLM([offer("1790.00")]))  # first counter must be <= 1800 and >= 1740
    assert offers(deal)[1]["price"] == "1790.00"
    deal2, _ = run(FakeLLM([offer("1760.00"), offer("1795.00")]))
    assert offers(deal2)[2]["source"] == "engine"  # 1795 is above the previous ask of 1760


def test_prompt_injection_from_the_client_cannot_move_the_price():
    llm = FakeLLM([offer("1.00", "Sure, I will give it away.")] * 5)
    deal, out = run(llm)
    assert out.price >= Money.of(1500)
    assert all(Decimal(o["price"]) >= 1500 for o in offers(deal))


def test_leaky_model_text_is_replaced_with_neutral_wording():
    deal, _ = run(FakeLLM([offer("1760.00", "My floor is 1500, honest guarantee.")]))
    msg = offers(deal)[1]["message"]
    assert "floor" not in msg and "guarantee" not in msg and "1760.00" in msg


def test_a_client_below_the_floor_ends_in_a_walk_away():
    deal, out = run(NoModel(), ceiling=1000, target=800, patience=3)
    assert out.status == "WALKED_AWAY" and deal.state == "WALKED_AWAY"
    assert deal.ledger.filter(kind="DEAL_WALKED_AWAY").count() == 1
    assert verify_ledger(deal) is None


def test_budget_exhaustion_degrades_to_engine_prices():
    llm = FakeLLM([offer("1760.00")] * 10)
    deal = open_deal("Brand kit", "client@example.com")
    negotiate(deal, CARD, "standard", freelancer(llm, per_deal=1), client(1650))
    assert len(llm.calls) == 1
    assert "BUDGET_EXCEEDED" in offers(deal)[-1]["notes"]


def test_agreed_terms_split_the_money_exactly():
    deal, out = run(NoModel())
    t = deal.terms
    paid = sum((Decimal(p["amount"]) for p in t["payouts"]), Decimal(0))
    assert paid + Decimal(t["freelancer_net"]) == Decimal(t["total"]) == out.price.amount
