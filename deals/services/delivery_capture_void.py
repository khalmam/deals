from django.db import transaction

from deals.domain.money import Money
from deals.domain.states import Event, transition
from deals.models import PaymentRecord

from .common import move
from .ledger import append


def confirm_delivery(deal, confirmed_by="client", now=None):
    transition(deal.state, Event.DELIVERY_CONFIRMED)
    with transaction.atomic():
        move(deal, Event.DELIVERY_CONFIRMED)
        deal.save()
        append(deal, "DELIVERY_CONFIRMED", {"confirmed_by": confirmed_by}, now)
    return deal


def capture(deal, payments, now=None):
    """Take the money. Only possible after confirmed delivery; a second call is refused."""
    transition(deal.state, Event.CAPTURE_DONE)
    total = Money.of(deal.total_amount, deal.currency)
    cap = payments.capture(str(deal.pk), deal.auth_id, total, True, "1")
    with transaction.atomic():
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
    transition(deal.state, Event.VOID)
    if deal.auth_id:
        payments.void(str(deal.pk), deal.auth_id)
    with transaction.atomic():
        move(deal, Event.VOID)
        deal.save()
        append(deal, "HOLD_VOIDED", {"auth_id": deal.auth_id}, now)
    return deal
