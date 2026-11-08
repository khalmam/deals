"""A visitor's negotiation from the browser: a hosted buyer agent, with the visitor's limits,
negotiates with a hosted provider through the ordinary protocol."""
import secrets
from decimal import Decimal, InvalidOperation

from agents.negotiating_buyer import BuyerPolicy, ProcurementAgent
from agents.protocol_client import ProtocolClient, ProtocolError

from .agent_registry import get_agent, register_agent
from .local_protocol import local_send

MAX_STEPS = 14
CEILING = Decimal(1_000_000)


def _money(value, name):
    try:
        amount = Decimal(str(value).strip())
    except InvalidOperation:
        raise ValueError(f"{name} is not a number") from None
    if not Decimal(1) <= amount <= CEILING or amount != amount.to_integral_value():
        raise ValueError(f"{name} must be a whole amount from 1 to {CEILING}")
    return amount


def run_for_visitor(provider_slug, bundle_id, max_price, target_price, after):
    """Returns the negotiation id once the negotiation has ended or the steps run out."""
    ceiling, target = _money(max_price, "max price"), _money(target_price, "target price")
    if target > ceiling:
        raise ValueError("the target price cannot be above the maximum")
    provider = get_agent(provider_slug)
    if provider is None or not provider.get("hosted"):
        raise ValueError("that provider answers from its own process, not from this page")
    bundle = next((s for s in provider["services"] if s.get("id") == bundle_id), None)
    if bundle is None:
        raise ValueError("that provider does not publish that bundle")
    currency = bundle["currency"]
    buyer = register_agent(
        name=f"Visitor {secrets.token_hex(3)}", agent_type="BUYER", owner_name="Demo visitor",
        owner_email="visitor@demo.invalid", is_public=False, hosted=True,
        mandate={"max_deal": str(ceiling), "currency": currency})
    agent = ProcurementAgent(ProtocolClient(local_send(buyer, after), ""), buyer.slug,
                             BuyerPolicy(ceiling, target, 30, 7, Decimal(5), currency))
    try:
        agent.start(provider_slug, bundle_id)
        for _ in range(MAX_STEPS):
            if agent.step() == "done":
                break
    except ProtocolError as exc:
        raise ValueError(str(exc)) from exc
    return agent.negotiation_id
