from django.db import transaction

from deals.domain.money import Money
from deals.domain.states import Event, transition
from deals.models import Deal, PaymentRecord

from .common import move
from .ledger import append


def _lock(deal):
    """Wait for any request already acting on this deal, then re-read it. A double-click or a
    retry then finds the state the first request left and is refused, not repeated. Call it
    inside transaction.atomic()."""
    list(Deal.objects.select_for_update().filter(pk=deal.pk))
    deal.refresh_from_db()


def confirm_delivery(deal, confirmed_by="client", now=None):
    with transaction.atomic():
        _lock(deal)
        transition(deal.state, Event.DELIVERY_CONFIRMED)
        move(deal, Event.DELIVERY_CONFIRMED)
        deal.save()
        append(deal, "DELIVERY_CONFIRMED", {"confirmed_by": confirmed_by}, now)
    return deal


def capture(deal, payments, now=None):
    """Take the money. Only possible after confirmed delivery; a second call is refused."""
    with transaction.atomic():
        _lock(deal)
        transition(deal.state, Event.CAPTURE_DONE)
        total = Money.of(deal.total_amount, deal.currency)
        cap = payments.capture(str(deal.pk), deal.auth_id, total, True, "1")
        PaymentRecord.objects.create(deal=deal, kind="CAPTURE", paypal_id=cap.capture_id,
                                     amount=total.amount, currency=total.currency,
                                     status=cap.status)
        move(deal, Event.CAPTURE_DONE)
        deal.save()
        append(deal, "CAPTURE_COMPLETED", {"capture_id": cap.capture_id,
                                           "amount": str(total.amount),
                                           "currency": total.currency,
                                           "status": cap.status}, now)
    return deal


def void(deal, payments, now=None):
    """Release the hold. Allowed until the money is captured."""
    with transaction.atomic():
        _lock(deal)
        transition(deal.state, Event.VOID)
        if deal.auth_id:
            payments.void(str(deal.pk), deal.auth_id)
        move(deal, Event.VOID)
        deal.save()
        append(deal, "HOLD_VOIDED", {"auth_id": deal.auth_id}, now)
    return deal
