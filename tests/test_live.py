import json
from decimal import Decimal

import pytest

from agents.freelancer import FreelancerAgent
from agents.intent import read_by_rules, read_intent
from agents.llm import NoModel
from agents.spend_guard import MemoryStore, SpendGuard
from deals.services.live_deal import Deps
from deals.services.negotiate_round import (
    NegotiationClosed,
    current_ask,
    play_round,
    start_negotiation,
)
from deals.services.open_deal import open_deal
from engine.demo_card import demo_card


class Said:
    def __init__(self, reply):
        self.reply = reply

    def complete(self, system, messages):
        return self.reply


class Broken:
    def complete(self, system, messages):
        raise RuntimeError("model down")


def guard(**kw):
    return SpendGuard(MemoryStore(), **kw)


@pytest.mark.parametrize("text,action,price", [
    ("can you do 1,300?", "OFFER", "1300.00"), ("how about 1.5k", "OFFER", "1500.00"),
    ("ok I accept", "ACCEPT", None), ("no thanks, I'm out", "WALK_AWAY", None),
    ("hello there", "UNCLEAR", None)])
def test_rules_reader(text, action, price):
    got = read_by_rules(text)
    assert got.action == action and (got.price == Decimal(price) if price else got.price is None)


def test_model_reading_is_used():
    got = read_intent(Said('{"action": "OFFER", "price": 1250}'), guard(), "d", "twelve fifty")
    assert (got.action, got.price, got.source) == ("OFFER", Decimal("1250.00"), "model")


def test_fenced_json_is_read():
    got = read_intent(Said('```json\n{"action": "ACCEPT", "price": null}\n```'), guard(), "d", "ok")
    assert got.action == "ACCEPT" and got.source == "model"


@pytest.mark.parametrize("llm,g", [
    (Broken(), guard()), (Said("sure thing!"), guard()), (Said('{"action": "OFFER"}'), guard()),
    (Said('{"action": "ACCEPT"}'), guard(per_deal=0))])
def test_model_trouble_falls_back_to_rules(llm, g):
    assert read_intent(llm, g, "d", "pay 900 and we are done").source == "rules"


@pytest.fixture
def live(db):
    deal = open_deal("Brand identity", "c@example.com")
    card = demo_card()
    start_negotiation(deal, card, "standard")
    return deal, card, FreelancerAgent(NoModel(), guard())


def test_counter_then_agree(live):
    deal, card, fl = live
    assert current_ask(deal).amount == Decimal("1800.00")
    out = play_round(deal, card, "standard", fl, "OFFER", Decimal("1200"), "can you do 1200?")
    assert out.status == "COUNTER" and out.price.amount < Decimal("1800")
    out = play_round(deal, card, "standard", fl, "OFFER", Decimal("1900"), "fine, 1900")
    assert out.status == "AGREED" and deal.terms_hash


def test_accept_takes_the_current_ask(live):
    deal, card, fl = live
    out = play_round(deal, card, "standard", fl, "ACCEPT", None, "ok")
    assert out.status == "AGREED" and out.price.amount == Decimal("1800.00")


def test_closed_negotiation_refuses_more(live):
    deal, card, fl = live
    play_round(deal, card, "standard", fl, "ACCEPT", None, "ok")
    with pytest.raises(NegotiationClosed):
        play_round(deal, card, "standard", fl, "OFFER", Decimal("100"), "again")


def test_client_can_walk_away(live):
    deal, card, fl = live
    out = play_round(deal, card, "standard", fl, "WALK_AWAY", None, "no thanks")
    assert out.status == "WALKED_AWAY"


@pytest.fixture
def deps(monkeypatch, db):
    g = guard()
    d = Deps(demo_card(), FreelancerAgent(NoModel(), g), None, g, NoModel(), None, None)
    monkeypatch.setattr("web.live_views.get_deps", lambda: d)
    return d


def post(client, path, body=None):
    return client.post(path, data=json.dumps(body or {}), content_type="application/json")


def test_api_flow(client, deps):
    made = post(client, "/api/deals")
    assert made.status_code == 201
    deal_id = made.json()["deal_id"]
    said = post(client, f"/api/deals/{deal_id}/offers", {"message": "can you do 1200?"})
    assert said.json()["status"] == "COUNTER" and said.json()["read_by"] == "rules"
    assert client.get(f"/api/deals/{deal_id}").json()["stage"] == "negotiating"
    page = client.get(f"/deals/{deal_id}/").content.decode()
    assert "data-say" in page and "Sealed record" in page


def test_unclear_message_asks_again(client, deps):
    deal_id = post(client, "/api/deals").json()["deal_id"]
    got = post(client, f"/api/deals/{deal_id}/offers", {"message": "hmm"}).json()
    assert got["status"] == "UNCLEAR"


def test_empty_message_and_unknown_deal(client, deps):
    deal_id = post(client, "/api/deals").json()["deal_id"]
    assert post(client, f"/api/deals/{deal_id}/offers", {"message": " "}).status_code == 400
    ghost = "00000000-0000-0000-0000-000000000000"
    assert post(client, f"/api/deals/{ghost}/offers", {"message": "900"}).status_code == 404


def test_start_page(client, db):
    assert b"Start negotiating" in client.get("/start/").content
