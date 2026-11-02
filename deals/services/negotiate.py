"""Run a negotiation. The engine decides every move; the model may only pick a price inside
the window the engine allows and word the message. Every move goes in the ledger."""
from dataclasses import dataclass

from django.db import transaction

from agents.prompts import Context
from agents.wording import neutral_message
from deals.domain.money import Money, MoneyError
from deals.domain.states import Event
from engine.negotiation import Offer, opening_ask, respond, validate_offer
from engine.pricing import payout_plan

from .common import move
from .ledger import append
from .open_deal import agree_terms

DEFAULT_NET_DAYS = "7"
DEFAULT_LATE_FEE_PCT = "5"


@dataclass(frozen=True)
class Outcome:
    status: str  # AGREED or WALKED_AWAY
    price: Money | None
    rounds: int


def build_terms(bundle, price):
    plan = payout_plan(bundle, price)
    return {
        "bundle": bundle.id, "bundle_name": bundle.name, "total": str(price.amount),
        "currency": price.currency, "list_price": str(bundle.list_price.amount),
        "line_items": [{"name": i.name, "amount": str(i.total.amount)} for i in bundle.items],
        "payouts": [{"sub_id": s, "amount": str(m.amount)} for s, m in plan.subs],
        "freelancer_net": str(plan.freelancer_net.amount),
        "net_days": DEFAULT_NET_DAYS, "late_fee_pct": DEFAULT_LATE_FEE_PCT,
    }


def _walk_away(deal, by, reason, rounds, now):
    with transaction.atomic():
        move(deal, Event.WALK_AWAY)
        deal.save()
        append(deal, "DEAL_WALKED_AWAY", {"by": by, "reason": reason}, now)
    return Outcome("WALKED_AWAY", None, rounds)


def _pick_price(card, bundle, decision, ask, proposal):
    """The model's price counts only if it is inside the engine's window and the card."""
    notes = list(proposal.notes)
    reply = proposal.reply
    if reply and reply.action == "OFFER":
        try:
            cand = Money(reply.price, bundle.currency)
        except MoneyError:
            cand = None
        if (cand is not None and decision.price <= cand <= ask
                and validate_offer(card, Offer(bundle.id, cand)).ok):
            return cand, "model", notes
        notes.append("PRICE_OUTSIDE_WINDOW")
    return decision.price, "engine", notes


def negotiate(deal, card, bundle_id, freelancer, client, rounds=5, now=None):
    bundle, ref = card.get(bundle_id), str(deal.pk)
    ask = opening_ask(card, bundle_id).price
    msg = neutral_message("ASK", ask, bundle.name)
    append(deal, "OFFER_MADE", {"by": "freelancer", "bundle": bundle_id, "currency": ask.currency,
                                "price": str(ask.amount), "source": "rate_card", "message": msg},
           now)
    history = [("freelancer", msg)]
    for k in range(1, rounds + 2):
        offer = client.next(ask, k - 1)
        if offer.action == "WALK_AWAY":
            append(deal, "COUNTER_MADE", {"by": "client", "action": "WALK_AWAY",
                                          "message": offer.message}, now)
            return _walk_away(deal, "client", "out of patience", k, now)
        append(deal, "COUNTER_MADE", {"by": "client", "price": str(offer.price.amount),
                                      "currency": offer.price.currency,
                                      "message": offer.message}, now)
        history.append(("client", offer.message))
        d = respond(card, bundle_id, offer.price, k, rounds)
        if d.action == "ACCEPT":
            agree_terms(deal, build_terms(bundle, d.price), now)
            return Outcome("AGREED", d.price, k)
        if d.action == "WALK_AWAY":
            return _walk_away(deal, "freelancer", d.reason, k, now)
        ctx = Context(bundle.name, tuple(i.name for i in bundle.items), bundle.currency,
                      d.price.amount, ask.amount, offer.price.amount, offer.message, k,
                      tuple(history[-6:]))
        proposal = freelancer.propose(ref, ctx)
        price, source, notes = _pick_price(card, bundle, d, ask, proposal)
        use_model_text = source == "model" and proposal.reply.message
        msg = proposal.reply.message if use_model_text else neutral_message("ASK", price,
                                                                          bundle.name)
        append(deal, "OFFER_MADE", {"by": "freelancer", "bundle": bundle_id,
                                    "currency": price.currency, "price": str(price.amount),
                                    "source": source, "notes": notes, "message": msg}, now)
        history.append(("freelancer", msg))
        ask = price
    raise AssertionError("unreachable: respond() ends the loop by round rounds + 1")
