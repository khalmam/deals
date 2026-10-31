from django.db import models

from .deal import Deal


class LedgerEntry(models.Model):
    """Append-only. On Postgres a trigger blocks UPDATE, DELETE and TRUNCATE.
    ts is stored as the exact string that was hashed, so it never drifts."""
    deal = models.ForeignKey(Deal, on_delete=models.PROTECT, related_name="ledger")
    seq = models.PositiveIntegerField()
    kind = models.CharField(max_length=40)
    payload = models.JSONField()
    ts = models.CharField(max_length=40)
    prev_hash = models.CharField(max_length=64)
    hash = models.CharField(max_length=64)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["deal", "seq"], name="uniq_deal_seq")]
        ordering = ["deal", "seq"]
