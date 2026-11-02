"""The rules an agent must stay inside. The model may propose anything; this decides. Pure."""
from dataclasses import dataclass
from decimal import Decimal

from deals.domain.money import Money

from .catalog import CatalogError


@dataclass(frozen=True)
class Offer:
    bundle_id: str
    price: Money
    net_days: int = 0
    late_fee_pct: Decimal = Decimal("0")

    def __post_init__(self):
        if isinstance(self.late_fee_pct, float):
            raise TypeError("late_fee_pct must be a Decimal, int or str, not a float")
        object.__setattr__(self, "late_fee_pct", Decimal(self.late_fee_pct))


@dataclass(frozen=True)
class Verdict:
    ok: bool
    reasons: tuple = ()


@dataclass(frozen=True)
class Decision:
    action: str  # ASK, ACCEPT or WALK_AWAY
    price: Money | None = None
    reason: str = ""


def validate_offer(card, offer):
    """Is this offer inside the card? Reasons are fixed codes, never free text."""
    try:
        bundle = card.get(offer.bundle_id)
    except CatalogError:
        return Verdict(False, ("UNKNOWN_BUNDLE",))
    if offer.price.currency != bundle.currency:
        return Verdict(False, ("CURRENCY_MISMATCH",))
    reasons = []
    if offer.price < bundle.floor:
        reasons.append("BELOW_FLOOR")
    if bundle.list_price < offer.price:
        reasons.append("ABOVE_LIST")
    if not 0 <= offer.net_days <= card.policy.max_net_days:
        reasons.append("NET_DAYS_OUT_OF_RANGE")
    if not 0 <= offer.late_fee_pct <= card.policy.max_late_fee_pct:
        reasons.append("LATE_FEE_OUT_OF_RANGE")
    return Verdict(not reasons, tuple(reasons))


def _level(bundle, step, rounds):
    """Our asking price after `step` concessions: list price, sliding to the floor."""
    gap = bundle.list_price - bundle.floor
    return bundle.list_price - gap.times(Decimal(min(step, rounds)) / Decimal(rounds))


def opening_ask(card, bundle_id):
    return Decision("ASK", card.get(bundle_id).list_price, "opening ask from the rate card")


def respond(card, bundle_id, client_price, k, rounds=5):
    """Reply to the client's k-th offer (k starts at 1). Concede evenly from list to floor
    over `rounds` counters. Accept anything at or above our current ask. Never go below the
    floor, never above list. This is also the fallback when the model's offer is rejected."""
    bundle = card.get(bundle_id)
    if client_price.currency != bundle.currency:
        raise ValueError("currency mismatch")
    if k < 1 or rounds < 1:
        raise ValueError("k and rounds must be at least 1")
    ask_before = _level(bundle, k - 1, rounds)
    if not client_price < ask_before:
        capped = client_price if client_price <= bundle.list_price else bundle.list_price
        return Decision("ACCEPT", capped, "client met our ask")
    if k > rounds:
        return Decision("WALK_AWAY", None, "client stayed below our floor")
    return Decision("ASK", _level(bundle, k, rounds), f"counter {k} of {rounds}")
