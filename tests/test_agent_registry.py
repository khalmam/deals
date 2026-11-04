import hashlib

import pytest
from django.test import Client
from django.utils import timezone

from deals.models import AgentProfile
from deals.services.agent_registry import (
    authenticate_agent,
    discover_agents,
    issue_credential,
    register_agent,
)


@pytest.mark.django_db
def test_register_agent_creates_independent_identity():
    agent = register_agent(
        name="Northstar Backend", agent_type="PROVIDER", owner_name="Ibrahim",
        owner_email="owner@example.com", capabilities=["Django", "PostgreSQL"],
    )
    assert agent.slug == "northstar-backend"
    assert agent.agent_type == AgentProfile.PROVIDER
    assert agent.capabilities == ["Django", "PostgreSQL"]


@pytest.mark.django_db
def test_credential_is_hashed_and_authenticates_agent():
    agent = register_agent(
        name="Buyer One", agent_type="BUYER", owner_name="Client",
        owner_email="client@example.com",
    )
    credential, token = issue_credential(agent)
    credential.refresh_from_db()
    assert credential.digest == hashlib.sha256(token.encode()).hexdigest()
    assert token not in credential.digest
    assert authenticate_agent(token, "directory:read") == agent
    assert authenticate_agent(token, "payments:capture") is None


@pytest.mark.django_db
def test_revoked_and_expired_credentials_are_rejected():
    agent = register_agent(
        name="Buyer Two", agent_type="BUYER", owner_name="Client",
        owner_email="client2@example.com",
    )
    credential, token = issue_credential(agent)
    credential.expires_at = timezone.now()
    credential.save(update_fields=["expires_at"])
    assert authenticate_agent(token) is None


@pytest.mark.django_db
def test_discovery_only_returns_public_active_agents():
    visible = register_agent(
        name="Public Django Provider", agent_type="PROVIDER", owner_name="A",
        owner_email="a@example.com", capabilities=["Django", "REST APIs"],
    )
    register_agent(
        name="Private Provider", agent_type="PROVIDER", owner_name="B",
        owner_email="b@example.com", is_public=False,
    )
    register_agent(
        name="Paused Provider", agent_type="PROVIDER", owner_name="C",
        owner_email="c@example.com", status=AgentProfile.PAUSED,
    )
    assert [item["id"] for item in discover_agents(capability="django")] == [str(visible.pk)]


@pytest.mark.django_db
def test_public_directory_and_private_identity_endpoint():
    agent = register_agent(
        name="API Provider", agent_type="PROVIDER", owner_name="Owner",
        owner_email="owner@example.com", mandate={"max_amount": "100"},
    )
    _, token = issue_credential(agent)
    client = Client()
    public = client.get("/api/agents")
    assert public.status_code == 200
    assert "mandate" not in public.json()["results"][0]
    assert client.get("/api/agents/me").status_code == 401
    private = client.get("/api/agents/me", HTTP_AUTHORIZATION=f"Bearer {token}")
    assert private.status_code == 200
    assert private.json()["id"] == str(agent.pk)
