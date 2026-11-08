"""A provider agent that Deals runs for its owner. It is an ordinary client of the protocol:
it reads the history and answers through submit_message, the same entry point the HTTP API
uses, so it passes every check an external provider would. Its floor stays inside this
module; no message or error ever carries it."""
from decimal import ROUND_HALF_UP, Decimal

from deals.domain.money import Money
from deals.models import Negotiation, NegotiationMessage
from engine.negotiation import respond
from engine.profile_card import card_from_services

from .negotiation_protocol import submit_message

ROUNDS = 5


def _decide(card, head, buyer_offers):
    """The hosted strategy: the rules engine's concession ladder plus the card's policy."""
    terms = head.terms
    price = Money.of(terms["price"]["amount"], terms["price"]["currency"])
    verdict = respond(card, terms["bundle_id"], price, buyer_offers, ROUNDS)
    if verdict.action == "WALK_AWAY":
        return {"type": "REJECT"}
    policy = card.policy
    fee = min(Decimal(terms["late"]["fee_pct"]), policy.max_late_fee_pct)
    price_out = terms["price"] if verdict.action == "ACCEPT" else {
        **terms["price"], "amount": str(verdict.price.amount.quantize(Decimal("0.01"),
                                                                       ROUND_HALF_UP))}
    wanted = {**terms, "price": price_out,
              "payment": {"net_days": min(terms["payment"]["net_days"], policy.max_net_days)},
              "late": {**terms["late"], "fee_pct": format(fee.normalize(), "f") if fee else "0"}}
    if verdict.action == "ACCEPT" and wanted == terms:
        return {"type": "ACCEPT", "terms_hash": head.terms_hash}
    return {"type": "COUNTER", "terms": wanted}


def hosted_reply(negotiation_id, now=None):
    """Answer the standing buyer proposal if the provider is hosted and it is its turn."""
    neg = Negotiation.objects.select_related("deal__provider").get(pk=negotiation_id)
    provider = neg.deal.provider
    if not provider.hosted or neg.status != "OPEN":
        return None
    head = NegotiationMessage.objects.get(pk=neg.head_proposal_id)
    if head.sender_id == provider.pk:
        return None
    card = card_from_services(provider.services)
    offers = neg.messages.filter(sender=neg.deal.buyer).count()
    body = {**_decide(card, head, offers), "in_reply_to": str(head.proposal_id)}
    return submit_message(provider, negotiation_id, body, f"hosted:{head.proposal_id}", now)
