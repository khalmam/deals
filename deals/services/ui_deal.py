"""Starts the chat haggle against a hosted provider picked on the start page. A throwaway hosted
buyer is registered for the visitor, as the buyer-agent page does, and the deal opens through
start_agent_deal, the code agents use, so the chat runs against the provider's own rate card."""
import secrets
from decimal import Decimal

from .agent_deals import AgentDealError, start_agent_deal
from .agent_registry import discover_agents, get_agent, register_agent


def hosted_providers():
    return [a for a in discover_agents(agent_type="PROVIDER")
            if a["hosted"] and any(s.get("list_price") for s in a["services"])]


def priced_providers():
    """Every public provider with a priced service, those that can answer in the browser
    first. The rest are shown greyed out on the pick page."""
    found = [a for a in discover_agents(agent_type="PROVIDER")
             if any(s.get("list_price") for s in a["services"])]
    for a in found:  # what the pick cards show: the lowest price and how many services
        priced = [s for s in a["services"] if s.get("list_price")]
        low = min(priced, key=lambda s: Decimal(str(s["list_price"])))
        a["from_price"] = f"{Decimal(str(low['list_price'])):.0f}"
        a["from_currency"], a["service_count"] = low.get("currency", ""), len(priced)
    return sorted(found, key=lambda a: (not a["hosted"], a["name"].lower()))


def start_for_visitor(provider_slug, bundle_id, now=None):
    """Returns the new deal's id. The visitor may spend up to the service's list price."""
    provider = get_agent(provider_slug)
    if provider is None or not provider.get("hosted"):
        raise AgentDealError("that provider is not available here", 404)
    bundle = next((s for s in provider["services"]
                   if s.get("id") == bundle_id and s.get("list_price")), None)
    if bundle is None:
        raise AgentDealError("that provider does not publish that service", 404)
    buyer = register_agent(
        name=f"Visitor {secrets.token_hex(3)}", agent_type="BUYER", owner_name="Demo visitor",
        owner_email="visitor@demo.invalid", is_public=False, hosted=True,
        mandate={"max_deal": str(bundle["list_price"]), "currency": bundle["currency"]})
    return start_agent_deal(buyer, provider_slug, bundle_id, now=now)
