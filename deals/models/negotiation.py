import uuid

from django.db import models

from .agent import AgentProfile
from .deal import Deal


class Negotiation(models.Model):
    """Where a negotiation stands. The status changes; the messages never do."""

    deal = models.OneToOneField(Deal, primary_key=True, on_delete=models.PROTECT,
                                related_name="negotiation")
    status = models.CharField(max_length=10, default="OPEN")
    head_version = models.PositiveIntegerField(default=0)
    head_proposal_id = models.UUIDField(null=True, blank=True)
    closed_at = models.CharField(max_length=40, blank=True)


class NegotiationMessage(models.Model):
    """Append-only. Rows are never updated or deleted; on Postgres a trigger enforces it."""

    proposal_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    negotiation = models.ForeignKey(Negotiation, on_delete=models.PROTECT,
                                    related_name="messages")
    version = models.PositiveIntegerField()
    msg_type = models.CharField(max_length=10)
    in_reply_to = models.UUIDField(null=True, blank=True)
    sender = models.ForeignKey(AgentProfile, on_delete=models.PROTECT, related_name="+")
    terms = models.JSONField(default=dict, blank=True)  # empty unless PROPOSE or COUNTER
    terms_hash = models.CharField(max_length=64)  # for ACCEPT, REJECT, WITHDRAW: the head's
    prev_hash = models.CharField(max_length=64)
    message_hash = models.CharField(max_length=64)
    expires_at = models.CharField(max_length=40, blank=True)
    created_at = models.CharField(max_length=40)
    idempotency_key = models.CharField(max_length=80)
    request_hash = models.CharField(max_length=64)

    class Meta:
        ordering = ["negotiation", "version"]
        constraints = [
            models.UniqueConstraint(fields=["negotiation", "version"], name="uniq_neg_version"),
            models.UniqueConstraint(fields=["sender", "idempotency_key"], name="uniq_neg_key"),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise RuntimeError("negotiation messages are immutable")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise RuntimeError("negotiation messages are immutable")
