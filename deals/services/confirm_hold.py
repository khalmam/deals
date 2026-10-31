from django.db import transaction

from deals.domain.money import Money
from deals.domain.states import Event, transition

from .common import move
from .ledger import append


class TermsMismatch(Exception):
    """The hold PayPal created does not match the agreed terms."""


def confirm_hold(deal, payments, now=None):
    """After the client approves on PayPal: authorize, then check PayPal's own record
    carries our terms hash and the agreed amount. If not, release the hold."""
    transition(deal.state, Event.HOLD_APPROVED)
    ref = str(deal.pk)
    auth = payments.authorize(ref, deal.order_id)
    seen = payments.get_authorization(auth.auth_id)
    if seen.custom_id != deal.terms_hash or seen.amount != Money.of(deal.total_amount,
                                                                    deal.currency):
        payments.void(ref, auth.auth_id)
        raise TermsMismatch("PayPal's hold does not match the agreed terms; it was released")
    with transaction.atomic():
        deal.auth_id, deal.authorization_expires = auth.auth_id, auth.expires_at
        move(deal, Event.HOLD_APPROVED)
        deal.save()
        append(deal, "HOLD_AUTHORIZED", {"order_id": deal.order_id, "auth_id": auth.auth_id,
                                         "expires_at": auth.expires_at,
                                         "terms_hash": deal.terms_hash}, now)
    return deal
