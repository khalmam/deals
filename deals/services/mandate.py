from django.db import transaction

from deals.domain.mandate import Mandate

from .ledger import append


def set_mandate(deal, mandate: Mandate, now=None):
    """The owner sets the rules once, before the agent acts. Recorded in the ledger."""
    with transaction.atomic():
        deal.mandate = mandate.to_dict()
        deal.save()
        append(deal, "MANDATE_SET", mandate.to_dict(), now)
    return deal
