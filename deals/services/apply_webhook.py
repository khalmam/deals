from django.db import transaction

from deals.domain.payout import DONE, ITEM_EVENT_PREFIX, WebhookOutcome
from deals.domain.states import Event, transition
from deals.models import PaymentRecord
from deals.models import WebhookEvent as WebhookRow

from .common import move
from .ledger import append

PREFIX = ITEM_EVENT_PREFIX


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
        append(deal, "PAYOUT_ITEM_SUCCEEDED" if status == DONE else "WEBHOOK_APPLIED",
               {"item": rec.paypal_id, "status": status, "source": source_id,
                "payout_item_id": payout_item_id}, now)
        items = deal.payments.filter(kind="PAYOUT_ITEM")
        if status == DONE and not items.exclude(status=DONE).exists():
            transition(deal.state, Event.PAYOUT_DONE)
            move(deal, Event.PAYOUT_DONE)
            deal.save()
    return True


def apply_webhook(event, now=None):
    """Apply one verified PayPal event. A repeated event id is ignored once it has been handled;
    a payout-item event that failed half-way is picked up again when PayPal retries it."""
    row, created = WebhookRow.objects.get_or_create(
        event_id=event.event_id,
        defaults={"event_type": event.event_type, "resource_id": event.resource_id})
    is_item = event.event_type.startswith(PREFIX)
    if not created and (row.applied or not is_item):
        return WebhookOutcome.DUPLICATE.value
    if not is_item:
        return WebhookOutcome.IGNORED.value
    rec = PaymentRecord.objects.filter(kind="PAYOUT_ITEM",
                                       paypal_id=_sender_item_id(event.resource)).first()
    if rec is None:
        return WebhookOutcome.UNKNOWN_ITEM.value
    record_item_status(rec, event.event_type[len(PREFIX):], event.event_id, event.resource_id, now)
    row.applied = True
    row.save()
    return WebhookOutcome.APPLIED.value
