from django.db import IntegrityError, transaction

from deals.domain.states import Event, transition
from deals.models import PaymentRecord
from deals.models import WebhookEvent as WebhookRow

from .common import move
from .ledger import append

PREFIX = "PAYMENT.PAYOUTS-ITEM."


def _sender_item_id(resource):
    return (resource.get("payout_item", {}) or {}).get("sender_item_id") \
        or resource.get("sender_item_id", "")


def record_item_status(rec, status, source_id, payout_item_id, now=None):
    """Store one payout item's new status. When every item has succeeded the deal is PAID_OUT.
    Shared by the webhook and the Refresh button, so both reach the same state."""
    if rec.status == status:
        return False
    with transaction.atomic():
        rec.status = status
        rec.save()
        deal = rec.deal
        append(deal, "PAYOUT_ITEM_SUCCEEDED" if status == "SUCCEEDED" else "WEBHOOK_APPLIED",
               {"item": rec.paypal_id, "status": status, "source": source_id,
                "payout_item_id": payout_item_id}, now)
        items = deal.payments.filter(kind="PAYOUT_ITEM")
        if status == "SUCCEEDED" and not items.exclude(status="SUCCEEDED").exists():
            transition(deal.state, Event.PAYOUT_DONE)
            move(deal, Event.PAYOUT_DONE)
            deal.save()
    return True


def apply_webhook(event, now=None):
    """Apply one verified PayPal event. A repeated event id is ignored."""
    try:
        with transaction.atomic():
            row = WebhookRow.objects.create(event_id=event.event_id, event_type=event.event_type,
                                            resource_id=event.resource_id)
    except IntegrityError:
        return "DUPLICATE"
    if not event.event_type.startswith(PREFIX):
        return "IGNORED"
    rec = PaymentRecord.objects.filter(kind="PAYOUT_ITEM",
                                       paypal_id=_sender_item_id(event.resource)).first()
    if rec is None:
        return "UNKNOWN_ITEM"
    record_item_status(rec, event.event_type[len(PREFIX):], event.event_id, event.resource_id, now)
    row.applied = True
    row.save()
    return "APPLIED"
