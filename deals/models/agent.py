import uuid

from django.db import models


class AgentProfile(models.Model):
    """A durable identity for an independently operated commerce agent."""

    PROVIDER = "PROVIDER"
    BUYER = "BUYER"
    AGENT_TYPES = [(PROVIDER, "Provider"), (BUYER, "Buyer")]
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    STATUSES = [(ACTIVE, "Active"), (PAUSED, "Paused")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=120, unique=True)
    agent_type = models.CharField(max_length=12, choices=AGENT_TYPES)
    owner_name = models.CharField(max_length=120)
    owner_email = models.EmailField()
    description = models.TextField(max_length=1000, blank=True)
    endpoint_url = models.URLField(max_length=500, blank=True)
    protocol = models.CharField(max_length=12, default="DEALS")
    hosted = models.BooleanField(default=False)  # True: Deals runs this agent for its owner
    capabilities = models.JSONField(default=list, blank=True)
    services = models.JSONField(default=list, blank=True)
    mandate = models.JSONField(default=dict, blank=True)
    is_public = models.BooleanField(default=True)
    status = models.CharField(max_length=10, choices=STATUSES, default=ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.agent_type.lower()})"


class AgentCredential(models.Model):
    """Only a digest is stored; the raw token is shown once when issued."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    agent = models.ForeignKey(AgentProfile, on_delete=models.CASCADE, related_name="credentials")
    prefix = models.CharField(max_length=12, unique=True)
    digest = models.CharField(max_length=64, unique=True)
    scopes = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.agent.slug}:{self.prefix}"
