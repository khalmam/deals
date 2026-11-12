from django.db import transaction

from deals.domain.mandate import Mandate, check_payouts
from deals.domain.money import Money
from deals.domain.ports import PayoutItem
from deals.domain.states import Event, transition
from deals.models import Deal, PaymentRecord

from .common import move
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


def settle_without_payouts(deal, now=None):
    """A captured deal that owes no sub-contractor has nothing left to wait for, so it is
    finished. Safe to call at any time: it acts only on a CAPTURED deal with no payouts."""
    with transaction.atomic():
        list(Deal.objects.select_for_update().filter(pk=deal.pk))
        deal.refresh_from_db()
        if deal.state != "CAPTURED" or (deal.terms or {}).get("payouts"):
            return False
        move(deal, Event.PAYOUT_DONE)
        deal.save()
        append(deal, "PAYOUT_SENT", {"batch_id": "", "actor": "system", "items": []}, now)
    return True
