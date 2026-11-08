"""What a message does besides being recorded: its expiry, the agreed terms it produces, and
the checks on what an agent commits itself to."""
from datetime import datetime, timedelta

from deals.domain.money import Money
from deals.domain.proposal import WITH_TERMS, ProposalError, terms_hash
from engine.profile_card import card_from_services

from .agent_deals import budget_of
from .negotiate import build_terms
from .negotiation_rules import NegotiationError
from .open_deal import agree_terms

FMT = "%Y-%m-%dT%H:%M:%S.%fZ"
DEFAULT_EXPIRY, MIN_EXPIRY, MAX_EXPIRY = 86400, 60, 604800


def plus(ts, seconds):
    return (datetime.strptime(ts, FMT) + timedelta(seconds=seconds)).strftime(FMT)


def expiry_seconds(body, msg_type):
    if "expires_in" not in body:
        return DEFAULT_EXPIRY if msg_type in WITH_TERMS else None
    value = body["expires_in"]
    if msg_type not in WITH_TERMS or isinstance(value, bool) or not isinstance(value, int) \
            or not MIN_EXPIRY <= value <= MAX_EXPIRY:
        raise ProposalError(f"expires_in is {MIN_EXPIRY} to {MAX_EXPIRY} seconds and applies "
                            "to PROPOSE and COUNTER only")
    return value


def money_of(terms):
    return Money.of(terms["price"]["amount"], terms["price"]["currency"])


def agree_proposal(neg, terms, proposal_id, now):
    """Turn the exact terms of the accepted proposal into the deal's agreed terms."""
    card = card_from_services(neg.deal.provider.services, require_floor=False)
    agreed = build_terms(card.get(terms["bundle_id"]), money_of(terms))
    agreed.update({
        "net_days": str(terms["payment"]["net_days"]), "late_fee_pct": terms["late"]["fee_pct"],
        "grace_days": str(terms["late"]["grace_days"]),
        "delivery_days": str(terms["delivery_days"]),
        "delivery_due": plus(now, terms["delivery_days"] * 86400)[:10],
        "proposal_id": str(proposal_id), "proposal_terms_hash": terms_hash(terms),
        "negotiation_id": str(neg.pk)})
    agree_terms(neg.deal, agreed, now)


def guard_own_price(neg, agent, role, price):
    """Safeguards on what an agent commits itself to. The messages go only to that agent."""
    if role == "buyer":
        limit = budget_of(neg.deal.buyer)
        if limit is None or price.currency != limit.currency or price.amount > limit.amount:
            raise NegotiationError("OVER_BUDGET", "that is above your own budget")
        return
    bundle_id = neg.deal.bundle_id
    floor = card_from_services(agent.services, require_floor=False).get(bundle_id).floor
    if floor.amount > 0 and price < floor:
        raise NegotiationError("BELOW_YOUR_FLOOR", "that is below the floor you configured", 422)
