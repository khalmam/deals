"""Wires the live flow from settings: model, spend cap, rate card, PayPal and the mandate."""
from functools import lru_cache

from django.conf import settings

from agents.actor import ActionAgent
from agents.freelancer import FreelancerAgent
from agents.spend_guard import MemoryStore, SpendGuard
from deals.domain.mandate import Mandate
from deals.services.live_deal import Deps
from engine.demo_card import demo_card

from .llm_factory import llm_from_settings
from .paypal_factory import payments_from_settings


@lru_cache(maxsize=1)
def live_deps():
    llm, _ = llm_from_settings()
    guard = SpendGuard(MemoryStore(), per_deal=40, total=300)  # caps the AWS bill
    # The demo flow pays one sub-contractor. Without DEMO_SUB_EMAIL it pays nobody, but it must
    # still start: the agent-to-agent flow brings its own mandate from the provider's profile.
    subs = {"illustrator": settings.DEMO_SUB_EMAIL} if settings.DEMO_SUB_EMAIL else {}
    mandate = Mandate(bool(subs), subs, allow_hold=True, allow_capture=True, allow_void=True)
    return Deps(demo_card(), FreelancerAgent(llm, guard), ActionAgent(llm, guard), guard, llm,
                payments_from_settings(), mandate)
