from django.db import transaction

from deals.domain.chain import Entry, make_entry, verify
from deals.models import Deal, LedgerEntry

from .common import utc_now


def _to_domain(row):
    return Entry(str(row.deal_id), row.seq, row.kind, row.payload, row.ts,
                 row.prev_hash, row.hash)


def append(deal, kind, payload, ts=None):
    """Add one entry. Locks the deal row so two writers cannot take the same seq."""
    with transaction.atomic():
        Deal.objects.select_for_update().get(pk=deal.pk)
        last = LedgerEntry.objects.filter(deal=deal).order_by("-seq").first()
        e = make_entry(_to_domain(last) if last else None, str(deal.pk), kind, payload,
                       ts or utc_now())
        return LedgerEntry.objects.create(deal=deal, seq=e.seq, kind=e.kind, payload=e.payload,
                                          ts=e.ts, prev_hash=e.prev_hash, hash=e.hash)


def verify_ledger(deal):
    """None if intact, else the index of the first bad entry."""
    return verify([_to_domain(r) for r in LedgerEntry.objects.filter(deal=deal).order_by("seq")])
