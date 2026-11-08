import pytest

from agents.freelancer import FreelancerAgent
from agents.llm import NoModel
from agents.spend_guard import MemoryStore, SpendGuard
from deals.services.live_deal import Deps
from tests.neg_helpers import MANDATE, Waiter, Wire, agent, bundle


@pytest.fixture
def wire(client, db, monkeypatch):
    guard = SpendGuard(MemoryStore(), per_deal=40, total=300)
    deps = Deps(None, FreelancerAgent(NoModel(), guard), Waiter(), guard, NoModel(), None, None)
    monkeypatch.setattr("web.negotiation_api.get_deps", lambda: deps)
    return Wire(client)


@pytest.fixture
def parties(wire):
    """A hosted provider (floor 1037 on the server), an external one (no floor published),
    and a buyer whose budget is 1400."""
    hosted, hosted_token = agent("Northstar", "PROVIDER", services=[bundle("1037")],
                                 mandate=MANDATE, hosted=True)
    outside, outside_token = agent("Freelance Ext", "PROVIDER", services=[bundle()],
                                   mandate=MANDATE)
    buyer, buyer_token = agent("Amanah Procurement", "BUYER",
                               mandate={"max_deal": "1400", "currency": "USD"})
    return {"hosted": hosted, "hosted_token": hosted_token, "outside": outside,
            "outside_token": outside_token, "buyer": buyer, "buyer_token": buyer_token}
