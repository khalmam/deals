import uuid

from django.db import models

from deals.domain.states import State


class Deal(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=200)
    client_email = models.EmailField()
    state = models.CharField(max_length=20, default=State.DRAFT.value,
                             choices=[(s.value, s.value) for s in State])
    terms = models.JSONField(default=dict)
    terms_hash = models.CharField(max_length=64, blank=True)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=3, default="USD")
    order_id = models.CharField(max_length=64, blank=True)
    approve_url = models.URLField(max_length=500, blank=True)
    auth_id = models.CharField(max_length=64, blank=True)
    authorization_expires = models.CharField(max_length=40, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
