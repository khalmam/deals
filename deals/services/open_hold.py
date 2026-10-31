from django.db import transaction

from deals.domain.money import Money
from deals.domain.states import Event, transition

from .common import move
from .ledger import append


def open_hold(deal, payments, return_url, cancel_url, now=None):
    """Ask PayPal for a hold. Returns the deal; deal.approve_url is where the client approves."""
    transition(deal.state, Event.HOLD_REQUESTED)  # refuse before touching PayPal
    total = Money.of(deal.total_amount, deal.currency)
    hold = payments.create_hold(str(deal.pk), total, deal.terms_hash, return_url, cancel_url)
    with transaction.atomic():
        deal.order_id, deal.approve_url = hold.order_id, hold.approve_url
        move(deal, Event.HOLD_REQUESTED)
        deal.save()
        append(deal, "HOLD_REQUESTED", {"order_id": hold.order_id}, now)
    return deal
