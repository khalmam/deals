"""One round of a live negotiation. Everything is rebuilt from the ledger, so the server keeps
nothing between calls. The engine decides; the model may only pick a price inside its window."""
from agents.prompts import Context
from agents.wording import neutral_message
from deals.domain.money import Money
from engine.negotiation import opening_ask, respond

from .ledger import append
from .negotiate import Outcome, _pick_price, _walk_away, build_terms
from .open_deal import agree_terms

ROUNDS = 5


class NegotiationClosed(Exception):
    """The deal was already agreed or abandoned."""


def start_negotiation(deal, card, bundle_id, now=None):
    bundle = card.get(bundle_id)
    ask = opening_ask(card, bundle_id).price
    append(deal, "OFFER_MADE", {"by": "freelancer", "bundle": bundle_id, "currency": ask.currency,
                                "price": str(ask.amount), "source": "rate_card",
                                "message": neutral_message("ASK", ask, bundle.name)}, now)
    return ask


def _state(deal):
    """(current ask, client offers so far, history, closed) read from the ledger."""
    ask, offers, history, closed = None, 0, [], False
    for e in deal.ledger.order_by("seq"):
        p = e.payload
        if e.kind in ("TERMS_AGREED", "DEAL_WALKED_AWAY"):
            closed = True
        elif e.kind == "OFFER_MADE":
            ask = Money.of(p["price"], p["currency"])
            history.append(("freelancer", p.get("message", "")))
        elif e.kind == "COUNTER_MADE":
            offers += 1
            history.append(("client", p.get("message", "")))
    return ask, offers, history, closed


def current_ask(deal):
    return _state(deal)[0]


def play_round(deal, card, bundle_id, freelancer, action, price, text, rounds=ROUNDS, now=None):
    """action is OFFER (with a price), ACCEPT (the current ask) or WALK_AWAY."""
    ask, offers, history, closed = _state(deal)
    if closed or ask is None:
        raise NegotiationClosed("this negotiation is over")
    k, bundle = offers + 1, card.get(bundle_id)
    if action == "WALK_AWAY":
        append(deal, "COUNTER_MADE", {"by": "client", "action": "WALK_AWAY", "message": text}, now)
        return _walk_away(deal, "client", "the client walked away", k, now)
    offer = ask if action == "ACCEPT" else Money.of(price, bundle.currency)
    append(deal, "COUNTER_MADE", {"by": "client", "price": str(offer.amount),
                                  "currency": offer.currency, "message": text}, now)
    history.append(("client", text))
    d = respond(card, bundle_id, offer, k, rounds)
    if d.action == "ACCEPT":
        agree_terms(deal, build_terms(bundle, d.price), now)
        return Outcome("AGREED", d.price, k)
    if d.action == "WALK_AWAY":
        return _walk_away(deal, "freelancer", d.reason, k, now)
    ctx = Context(bundle.name, tuple(i.name for i in bundle.items), bundle.currency,
                  d.price.amount, ask.amount, offer.amount, text, k, tuple(history[-6:]))
    proposal = freelancer.propose(str(deal.pk), ctx)
    new, source, notes = _pick_price(card, bundle, d, ask, proposal)
    use_model = source == "model" and proposal.reply.message
    msg = proposal.reply.message if use_model else neutral_message("ASK", new, bundle.name)
    append(deal, "OFFER_MADE", {"by": "freelancer", "bundle": bundle_id, "currency": new.currency,
                                "price": str(new.amount), "source": source, "notes": notes,
                                "message": msg}, now)
    return Outcome("COUNTER", new, k)
