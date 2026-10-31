from django.db import transaction

from deals.domain.chain import terms_hash
from deals.domain.money import Money
from deals.domain.states import Event, transition
from deals.models import Deal

from .common import move
from .ledger import append


def open_deal(title, client_email, now=None):
    with transaction.atomic():
        deal = Deal.objects.create(title=title, client_email=client_email)
        append(deal, "DEAL_OPENED", {"title": title, "client_email": client_email}, now)
        move(deal, Event.START_NEGOTIATION)
        deal.save()
    return deal


def agree_terms(deal, terms, now=None):
    """terms must hold 'total' and 'currency' as strings. Floats are rejected by the hash."""
    transition(deal.state, Event.TERMS_AGREED)
    total = Money.of(terms["total"], terms["currency"])
    digest = terms_hash(terms)
    with transaction.atomic():
        deal.terms, deal.terms_hash = terms, digest
        deal.total_amount, deal.currency = total.amount, total.currency
        move(deal, Event.TERMS_AGREED)
        deal.save()
        append(deal, "TERMS_AGREED", {"terms_hash": digest, "total": str(total.amount),
                                      "currency": total.currency}, now)
    return deal
