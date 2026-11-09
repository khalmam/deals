from deals.domain.payout import NOT_YET, normalise
from deals.models import PaymentRecord

from .apply_webhook import record_item_status


def refresh_payouts(deal, payments, now=None):
    """The 'Refresh from PayPal' fallback: ask PayPal for the batch and apply what it says,
    exactly as a webhook would. Safe to run any number of times."""
    batch = deal.payments.filter(kind="PAYOUT_BATCH").first()
    if batch is None:
        return 0
    changed = 0
    for payout_item_id, status, sender_item_id in payments.get_payout(batch.paypal_id).items:
        if status in NOT_YET:
            continue
        rec = PaymentRecord.objects.filter(deal=deal, kind="PAYOUT_ITEM",
                                           paypal_id=sender_item_id).first()
        if rec and record_item_status(rec, normalise(status),
                                      f"poll:{batch.paypal_id}", payout_item_id, now):
            changed += 1
    deal.refresh_from_db()
    return changed
