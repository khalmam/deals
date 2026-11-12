"""The chat negotiation shows the terms that come with the current price."""
import pytest

from agents.freelancer import FreelancerAgent
from agents.llm import NoModel
from agents.spend_guard import MemoryStore, SpendGuard
from deals.services.deal_view import build_deal_view
from deals.services.negotiate_round import play_round, start_negotiation
from deals.services.open_deal import open_deal
from engine.demo_card import demo_card


@pytest.fixture
def negotiating(db):
    deal = open_deal("Brand identity", "c@example.com")
    start_negotiation(deal, demo_card(), "standard")
    return deal


def test_terms_are_shown_before_agreement(negotiating):
    offer = build_deal_view(negotiating.pk)["offer"]
    assert offer is not None and offer["net_days"] != ""
    assert "Illustration set" in [d["name"] for d in offer["deliverables"]]


def test_no_preview_once_agreed(negotiating):
    freelancer = FreelancerAgent(NoModel(), SpendGuard(MemoryStore()))
    play_round(negotiating, demo_card(), "standard", freelancer, "ACCEPT", None, "ok")
    assert build_deal_view(negotiating.pk)["offer"] is None


def test_page_shows_the_terms_with_the_price(client, negotiating):
    page = client.get(f"/deals/{negotiating.pk}/").content.decode()
    assert "Terms with this price" in page and "Illustration set" in page
