"""Choosing a provider on /start/ and chatting against that provider's own rate card."""
import json

import pytest

from agents.freelancer import FreelancerAgent
from agents.llm import NoModel
from agents.spend_guard import MemoryStore, SpendGuard
from deals.models import Deal
from deals.services.live_deal import Deps
from deals.services.ui_deal import hosted_providers
from engine.demo_card import demo_card


@pytest.fixture
def deps(monkeypatch, db):
    g = SpendGuard(MemoryStore())
    d = Deps(demo_card(), FreelancerAgent(NoModel(), g), None, g, NoModel(), None, None)
    monkeypatch.setattr("web.live_views.get_deps", lambda: d)
    return d


def post(client, path, body=None):
    return client.post(path, data=json.dumps(body or {}), content_type="application/json")


def test_start_page_lists_hosted_providers(client, parties):
    provider = hosted_providers()[0]
    page = client.get("/start/").content.decode()
    assert "data-provider" in page and provider["name"] in page
    assert "Sample freelancer" in page  # the default is still the demo haggle


def test_start_with_a_hosted_provider_opens_a_chat_deal(client, deps, parties):
    provider = hosted_providers()[0]
    service = next(s for s in provider["services"] if s.get("list_price"))
    got = post(client, "/api/ui/start", {"provider": provider["slug"], "bundle": service["id"]})
    assert got.status_code == 201
    deal = Deal.objects.select_related("provider", "buyer").get(pk=got.json()["deal_id"])
    assert deal.provider.slug == provider["slug"] and deal.buyer.hosted
    assert deal.bundle_id == service["id"]
    page = client.get(got.json()["deal_url"]).content.decode()
    assert "data-say" in page and provider["name"] in page


def test_chat_works_against_the_providers_own_card(client, deps, parties):
    provider = hosted_providers()[0]
    service = next(s for s in provider["services"] if s.get("list_price"))
    deal_id = post(client, "/api/ui/start",
                   {"provider": provider["slug"], "bundle": service["id"]}).json()["deal_id"]
    said = post(client, f"/api/deals/{deal_id}/offers", {"message": "can you do 500?"})
    assert said.status_code == 200 and said.json()["status"] != "UNCLEAR"


@pytest.mark.parametrize("body", [{"provider": "no-such-agent", "bundle": "standard"},
                                  {"provider": "", "bundle": ""}])
def test_unknown_provider_is_refused(client, deps, body):
    assert post(client, "/api/ui/start", body).status_code == 404
