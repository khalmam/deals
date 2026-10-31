from django.db import models

from .deal import Deal


class PaymentRecord(models.Model):
    deal = models.ForeignKey(Deal, on_delete=models.PROTECT, related_name="payments")
    kind = models.CharField(max_length=20)  # CAPTURE, REFUND, PAYOUT
    paypal_id = models.CharField(max_length=64, unique=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3)
    status = models.CharField(max_length=30, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class WebhookEvent(models.Model):
    """One row per PayPal event id, so a retried delivery is applied only once."""
    event_id = models.CharField(max_length=64, unique=True)
    event_type = models.CharField(max_length=80)
    resource_id = models.CharField(max_length=64, blank=True)
    received_at = models.DateTimeField(auto_now_add=True)
    applied = models.BooleanField(default=False)
