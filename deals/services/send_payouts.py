from django.db import transaction

from deals.domain.mandate import Mandate, check_payouts
from deals.domain.money import Money
from deals.domain.ports import PayoutItem
from deals.domain.states import Event, transition
from deals.models import PaymentRecord

from .ledger import append


class PayoutsAlreadySent(Exception):
    pass


def item_key(deal, sub_id):
    return f"{deal.pk}-{sub_id}"


def send_payouts(deal, payments, actor="agent", now=None):
    """Pay the approved sub-contractors from the agreed terms, once, after capture.
    The state stays CAPTURED until PayPal confirms every item (see apply_webhook)."""
    transition(deal.state, Event.PAYOUT_DONE)  # only possible after capture
    if deal.payments.filter(kind="PAYOUT_BATCH").exists():
        raise PayoutsAlreadySent("payouts for this deal were already sent")
    total = Money.of(deal.total_amount, deal.currency)
    owed = tuple((p["sub_id"], Money.of(p["amount"], deal.currency))
                 for p in deal.terms.get("payouts", []))
    lines = check_payouts(Mandate.from_dict(deal.mandate), owed, total)
    items = [PayoutItem(email, amt, item_key(deal, sub), "Deals payout")
             for sub, email, amt in lines]
    result = payments.send_payout(f"{deal.pk}-payout", items)
    with transaction.atomic():
        PaymentRecord.objects.create(deal=deal, kind="PAYOUT_BATCH", paypal_id=result.batch_id,
                                     amount=sum((a.amount for _, _, a in lines), 0 * total.amount),
                                     currency=total.currency, status=result.status)
        for sub, _, amt in lines:
            PaymentRecord.objects.create(deal=deal, kind="PAYOUT_ITEM",
                                         paypal_id=item_key(deal, sub), amount=amt.amount,
                                         currency=amt.currency, status="PENDING")
        append(deal, "PAYOUT_SENT", {"batch_id": result.batch_id, "actor": actor,
                                     "items": [{"sub_id": s, "amount": str(a.amount)}
                                               for s, _, a in lines]}, now)
    return deal
