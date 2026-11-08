"""Ties deals to agent identities: the provider's profile supplies the rate card and mandate,
the buyer's profile supplies the budget, and only the buyer may act on its own deals."""
from dataclasses import replace

from deals.domain.mandate import Mandate, MandateViolation
from deals.domain.money import Money, MoneyError
from deals.models import AgentProfile, Deal
from engine.catalog import CatalogError
from engine.profile_card import card_from_services

from .deal_view import DealNotFound
from .negotiate_round import start_negotiation
from .open_deal import open_deal

NEGOTIATE_SCOPE = "deals:negotiate"


class AgentDealError(Exception):
    """The rules refused. The message is safe to show the calling agent."""

    def __init__(self, message, status=409):
        super().__init__(message)
        self.status = status


class AccessDenied(Exception):
    def __init__(self, message, status):
        super().__init__(message)
        self.status = status


def budget_of(buyer):
    """The most the buyer's owner lets it spend on one deal, or None if none was set."""
    raw = (buyer.mandate or {}).get("max_deal")
    if raw is None:
        return None
    try:
        return Money.of(str(raw), (buyer.mandate or {}).get("currency", "USD"))
    except MoneyError as exc:
        raise AgentDealError("the buyer's budget is not a valid amount") from exc


def check_provider(services, mandate_dict, require_floor=True):
    """(rate card, mandate) from a provider's published data, checked so a deal cannot
    dead-end. Used when a provider registers and again when a deal starts."""
    try:
        card = card_from_services(services, require_floor)
        mandate = Mandate.from_dict(mandate_dict)
    except (CatalogError, MandateViolation, ArithmeticError, ValueError) as exc:
        raise AgentDealError(str(exc)) from exc
    subs = {i.sub_id for b in card.bundles for i in b.items if i.sub_id}
    missing = sorted(subs - set(mandate.approved_subs))
    if missing:
        raise AgentDealError(f"the provider's mandate does not approve: {', '.join(missing)}")
    return card, mandate


def start_agent_deal(buyer, provider_slug, bundle_id, title="", now=None):
    if buyer.agent_type != AgentProfile.BUYER:
        raise AgentDealError("only buyer agents can open deals", 403)
    limit = budget_of(buyer)
    if limit is None:
        raise AgentDealError("this buyer has no budget set, so it cannot negotiate", 403)
    provider = AgentProfile.objects.filter(
        slug=provider_slug, agent_type=AgentProfile.PROVIDER, status=AgentProfile.ACTIVE).first()
    if provider is None:
        raise AgentDealError("no such provider", 404)
    card, _ = check_provider(provider.services, provider.mandate)
    try:
        bundle = card.get(bundle_id)
    except CatalogError as exc:
        raise AgentDealError(str(exc), 404) from exc
    if bundle.currency != limit.currency or bundle.floor.amount > limit.amount:
        raise AgentDealError(f"the lowest price for {bundle.name} is above your budget of "
                             f"{limit.amount} {limit.currency}")
    deal = open_deal(title[:200] or f"{bundle.name} from {provider.name}", buyer.owner_email, now)
    deal.provider, deal.buyer, deal.bundle_id = provider, buyer, bundle.id
    deal.save()
    start_negotiation(deal, card, bundle.id, now)
    return str(deal.pk)


def for_deal(deps, deal_id):
    """The live dependencies with the provider's card and mandate swapped in, if it has one."""
    deal = Deal.objects.select_related("provider").filter(pk=deal_id).first()
    if deal is None or deal.provider is None:
        return deps
    card, mandate = check_provider(deal.provider.services, deal.provider.mandate, False)
    return replace(deps, card=card, mandate=mandate, bundle_id=deal.bundle_id)


def check_budget(deal, amount):
    """Refuse a price above the buyer's budget before it reaches the negotiation."""
    limit = budget_of(deal.buyer) if deal.buyer_id else None
    if limit is None:
        return
    if amount.currency != limit.currency or amount.amount > limit.amount:
        raise AgentDealError(f"{amount.amount} {amount.currency} is above your budget of "
                             f"{limit.amount} {limit.currency}")


def check_access(deal_id, agent):
    """Deals opened by an agent answer only to that agent. Demo deals stay open."""
    deal = Deal.objects.select_related("buyer").filter(pk=deal_id).first()
    if deal is None:
        raise DealNotFound(str(deal_id))
    if deal.buyer_id is None or deal.buyer.hosted:
        return  # demo deals, and deals a visitor runs from the browser, answer to the page
    if agent is None:
        raise AccessDenied("This deal belongs to an agent. Send its bearer token.", 401)
    if agent.pk != deal.buyer_id:
        raise AccessDenied("This deal belongs to a different agent.", 403)
