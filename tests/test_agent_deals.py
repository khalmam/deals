import json
from decimal import Decimal

import pytest

from agents.actor import Choice
from agents.buyer_client import BuyerAgent
from agents.freelancer import FreelancerAgent
from agents.llm import NoModel
from agents.spend_guard import MemoryStore, SpendGuard
from agents.tools import WAIT
from deals.models import Deal
from deals.services.agent_registry import issue_credential, register_agent
from deals.services.live_deal import Deps
from engine.catalog import CatalogError
from engine.profile_card import card_from_services

BUNDLE = {"id": "standard", "name": "Standard", "currency": "USD", "floor": "1000", "items": [
    {"name": "Logo", "rate": 900}, {"name": "Art", "rate": 500, "sub_id": "illustrator",
                                    "sub_pct": 50}, {"name": "Social", "rate": 400}]}
MANDATE = {"allow_hold": True, "allow_capture": True, "allow_void": True, "allow_payouts": True,
           "approved_subs": {"illustrator": "sub@example.com"}}


class Waiter:
    def choose(self, ref, state, menu, facts):
        return Choice(WAIT, "test", "rules")


@pytest.fixture
def deps(monkeypatch, db):
    g = SpendGuard(MemoryStore(), per_deal=40, total=300)
    d = Deps(None, FreelancerAgent(NoModel(), g), Waiter(), g, NoModel(), None, None)
    monkeypatch.setattr("web.live_views.get_deps", lambda: d)
    return d


def make(name, kind, scopes=None, **fields):
    agent = register_agent(name=name, agent_type=kind, owner_name="Owner",
                           owner_email=f"{name.lower().replace(' ', '')}@example.com", **fields)
    return agent, issue_credential(agent, scopes)[1]


@pytest.fixture
def world(deps):
    provider, _ = make("Northstar", "PROVIDER", services=[BUNDLE, {"name": "just a label"}],
                       mandate=MANDATE)
    buyer, token = make("Acme Buyer", "BUYER", ["directory:read", "deals:negotiate"],
                        mandate={"max_deal": "1400", "currency": "USD"})
    return provider, buyer, token


def call(client, method, path, body=None, token=None):
    extra = {"HTTP_AUTHORIZATION": f"Bearer {token}"} if token else {}
    r = client.generic(method, path, json.dumps(body or {}), content_type="application/json",
                       **extra)
    return r.status_code, r.json()


def sender(client):
    return lambda method, path, payload, token: call(client, method, path, payload, token)


def test_card_comes_from_profile_and_skips_labels():
    card = card_from_services([BUNDLE, {"name": "label"}])
    assert card.get("standard").list_price.amount == Decimal("1800.00")
    assert card.get("standard").floor.amount == Decimal("1000.00")
    with pytest.raises(CatalogError):
        card_from_services([{"name": "label only"}])
    with pytest.raises(CatalogError):
        card_from_services([{**BUNDLE, "floor": "x"}])


def test_create_needs_a_valid_token_with_scope(client, world):
    body = {"provider": "northstar", "bundle": "standard"}
    assert call(client, "POST", "/api/deals", body, token="dl_nope")[0] == 401
    _, read_only = make("Reader", "BUYER", ["directory:read"],
                        mandate={"max_deal": "1400"})
    assert call(client, "POST", "/api/deals", body, token=read_only)[0] == 401


def test_agent_deal_uses_provider_rate_card(client, world):
    provider, buyer, token = world
    status, made = call(client, "POST", "/api/deals",
                        {"provider": "northstar", "bundle": "standard"}, token)
    assert status == 201 and made["ask"].startswith("1800.00")
    deal = Deal.objects.get(pk=made["deal_id"])
    assert (deal.provider, deal.buyer, deal.bundle_id) == (provider, buyer, "standard")


@pytest.mark.parametrize("body,status", [
    ({"provider": "ghost", "bundle": "standard"}, 404),
    ({"provider": "northstar", "bundle": "nope"}, 404)])
def test_unknown_provider_or_bundle(client, world, body, status):
    assert call(client, "POST", "/api/deals", body, world[2])[0] == status


def test_budget_below_floor_is_refused_at_start(client, deps):
    make("Pro", "PROVIDER", services=[BUNDLE], mandate=MANDATE)
    _, token = make("Poor Buyer", "BUYER", ["deals:negotiate"], mandate={"max_deal": "500"})
    status, body = call(client, "POST", "/api/deals", {"provider": "pro", "bundle": "standard"},
                        token)
    assert status == 409 and "budget" in body["error"]


def test_buyer_without_budget_cannot_negotiate(client, deps):
    make("Pro", "PROVIDER", services=[BUNDLE], mandate=MANDATE)
    _, token = make("No Budget", "BUYER", ["deals:negotiate"])
    assert call(client, "POST", "/api/deals", {"provider": "pro", "bundle": "standard"},
                token)[0] == 403


def test_provider_mandate_must_approve_its_subs(db):
    with pytest.raises(ValueError, match="illustrator"):
        make("Loose", "PROVIDER", services=[BUNDLE], mandate={"allow_hold": True})
    with pytest.raises(ValueError, match="rate card"):
        make("Broken", "PROVIDER", services=[{**BUNDLE, "floor": "x"}], mandate=MANDATE)


def test_offer_above_budget_is_refused_and_ledger_untouched(client, world):
    _, _, token = world
    deal_id = call(client, "POST", "/api/deals", {"provider": "northstar", "bundle": "standard"},
                   token)[1]["deal_id"]
    before = Deal.objects.get(pk=deal_id).ledger.count()
    status, body = call(client, "POST", f"/api/deals/{deal_id}/offers",
                        {"message": "I can pay 1500 USD."}, token)
    assert status == 409 and "budget" in body["error"]
    assert Deal.objects.get(pk=deal_id).ledger.count() == before


def test_only_the_owning_agent_can_act(client, world):
    _, _, token = world
    deal_id = call(client, "POST", "/api/deals", {"provider": "northstar", "bundle": "standard"},
                   token)[1]["deal_id"]
    path = f"/api/deals/{deal_id}/offers"
    msg = {"message": "I can pay 1300 USD."}
    assert call(client, "POST", path, msg)[0] == 401
    _, other = make("Other Buyer", "BUYER", ["deals:negotiate"], mandate={"max_deal": "9999"})
    assert call(client, "POST", path, msg, other)[0] == 403
    assert call(client, "POST", path, msg, token)[0] == 200


def test_buyer_agent_negotiates_end_to_end(client, world):
    _, _, token = world
    result = BuyerAgent(sender(client), token, 1400).negotiate("northstar", "standard")
    assert result["status"] == "AGREED"
    assert Decimal(result["price"]) <= Decimal(1400)
    assert Decimal(result["price"]) >= Decimal(1000)  # never under the provider's floor
    deal = Deal.objects.get(pk=result["deal_id"])
    assert deal.state == "AGREED" and deal.mandate["approved_subs"] == {
        "illustrator": "sub@example.com"}


def test_buyer_agent_discovers_providers(client, world):
    found = BuyerAgent(sender(client), world[2], 1400).find_providers()
    assert [a["slug"] for a in found] == ["northstar"]


def test_demo_flow_without_token_is_unchanged(client, deps):
    from engine.demo_card import demo_card
    object.__setattr__(deps, "card", demo_card())
    status, made = call(client, "POST", "/api/deals")
    assert status == 201 and "ask" not in made


def test_directory_never_exposes_floor_or_payout_splits(client, world):
    _, body = call(client, "GET", "/api/agents?type=PROVIDER")
    text = json.dumps(body)
    assert "floor" not in text and "sub_id" not in text and "sub_pct" not in text
    service = body["results"][0]["services"][0]
    assert service["list_price"] == "1800.00" and service["items"][0]["rate"] == "900.00"
    assert body["results"][0]["services"][1] == {"name": "just a label"}


def test_provider_detail_and_unknown_slug(client, world):
    status, body = call(client, "GET", "/api/agents/northstar")
    assert status == 200 and body["services"][0]["id"] == "standard"
    assert call(client, "GET", "/api/agents/ghost")[0] == 404
    assert call(client, "POST", "/api/agents/northstar")[0] == 405


def test_agent_named_me_cannot_shadow_the_identity_route(client, db):
    agent, _ = make("Me", "BUYER")
    assert agent.slug != "me"


def test_directory_page_shows_prices(client, world):
    page = client.get("/agents/").content.decode()
    assert "from 1800.00 USD" in page and "1000" not in page


def test_buyer_shortlist_ranks_cheapest_first(client, world):
    cheap = {**BUNDLE, "id": "lite", "floor": "300", "items": [{"name": "Logo", "rate": 600}]}
    make("Budget Studio", "PROVIDER", services=[cheap], mandate=MANDATE)
    make("Label Only", "PROVIDER", services=[{"name": "no prices"}])
    ranked = BuyerAgent(sender(client), world[2], 1400).shortlist()
    assert [a["slug"] for a in ranked] == ["budget-studio", "northstar"]
