"""Agent registration, credential issuance and public directory queries."""
import hashlib
import secrets
from datetime import timedelta

from django.utils import timezone
from django.utils.text import slugify

from deals.models import AgentCredential, AgentProfile

DEFAULT_SCOPES = ["directory:read"]


def _unique_slug(name):
    base = slugify(name)[:100] or "agent"
    candidate, suffix = base, 2
    while AgentProfile.objects.filter(slug=candidate).exists():
        candidate = f"{base[:110]}-{suffix}"
        suffix += 1
    return candidate


def register_agent(*, name, agent_type, owner_name, owner_email, **fields):
    if agent_type not in {AgentProfile.PROVIDER, AgentProfile.BUYER}:
        raise ValueError("Agent type must be PROVIDER or BUYER.")
    profile = AgentProfile.objects.create(
        name=name.strip(), slug=_unique_slug(name), agent_type=agent_type,
        owner_name=owner_name.strip(), owner_email=owner_email.strip(), **fields,
    )
    return profile


def issue_credential(agent, scopes=None, lifetime_days=90):
    """Return a one-time bearer token; persist only its SHA-256 digest."""
    token = f"dl_{secrets.token_urlsafe(32)}"
    prefix = token[:11]
    credential = AgentCredential.objects.create(
        agent=agent, prefix=prefix, digest=hashlib.sha256(token.encode()).hexdigest(),
        scopes=scopes or DEFAULT_SCOPES,
        expires_at=timezone.now() + timedelta(days=lifetime_days),
    )
    return credential, token


def authenticate_agent(token, required_scope=None):
    if not token or not token.startswith("dl_"):
        return None
    digest = hashlib.sha256(token.encode()).hexdigest()
    credential = AgentCredential.objects.select_related("agent").filter(
        digest=digest, revoked_at__isnull=True,
    ).first()
    if credential is None:
        return None
    now = timezone.now()
    if credential.expires_at and credential.expires_at <= now:
        return None
    if credential.agent.status != AgentProfile.ACTIVE:
        return None
    if required_scope and required_scope not in credential.scopes:
        return None
    AgentCredential.objects.filter(pk=credential.pk).update(last_used_at=now)
    return credential.agent


def discover_agents(*, query="", agent_type="", capability=""):
    agents = AgentProfile.objects.filter(is_public=True, status=AgentProfile.ACTIVE)
    if agent_type in {AgentProfile.PROVIDER, AgentProfile.BUYER}:
        agents = agents.filter(agent_type=agent_type)
    if query:
        from django.db.models import Q
        agents = agents.filter(Q(name__icontains=query) | Q(description__icontains=query))
    results = []
    for agent in agents:
        capabilities = agent.capabilities if isinstance(agent.capabilities, list) else []
        if capability and capability.lower() not in [str(item).lower() for item in capabilities]:
            continue
        results.append({
            "id": str(agent.id), "name": agent.name, "slug": agent.slug,
            "type": agent.agent_type, "description": agent.description,
            "capabilities": capabilities, "services": agent.services,
            "protocol": agent.protocol, "endpoint_available": bool(agent.endpoint_url),
        })
    return results
