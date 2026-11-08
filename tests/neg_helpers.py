"""Shared setup for the negotiation tests: agents, a send adapter, and recorded responses."""
import json

from agents.actor import Choice
from agents.protocol_client import ProtocolClient
from agents.tools import WAIT
from deals.services.agent_registry import issue_credential, register_agent

SCOPES = ["directory:read", "deals:negotiate"]
LOCAL_FLOOR = "1037"  # the external provider's private floor: must never reach the server
MANDATE = {"allow_hold": True, "allow_capture": True, "allow_void": True,
           "allow_payouts": True, "approved_subs": {"illustrator": "sub@example.com"}}
ITEMS = [{"name": "Logo", "rate": 900}, {"name": "Art", "rate": 500, "sub_id": "illustrator",
                                        "sub_pct": 50}, {"name": "Social", "rate": 400}]


def bundle(floor=None):
    return {"id": "standard", "name": "Standard", "currency": "USD", "items": ITEMS,
            **({"floor": floor} if floor else {})}


class Waiter:
    def choose(self, ref, state, menu, facts):
        return Choice(WAIT, "test", "rules")


def agent(name, kind, **fields):
    profile = register_agent(name=name, agent_type=kind, owner_name="Owner",
                             owner_email=f"{name.lower().replace(' ', '')}@example.com", **fields)
    return profile, issue_credential(profile, SCOPES)[1]


class Wire:
    """Sends requests through the Django test client and remembers every response body."""

    def __init__(self, client):
        self.client, self.seen = client, []

    def __call__(self, method, path, payload, token, headers=None):
        extra = {"HTTP_AUTHORIZATION": f"Bearer {token}"} if token else {}
        for name, value in (headers or {}).items():
            extra["HTTP_" + name.upper().replace("-", "_")] = value
        r = self.client.generic(method, path, json.dumps(payload or {}),
                                content_type="application/json", **extra)
        self.seen.append(r.content.decode())
        return r.status_code, r.json()

    def client_for(self, token):
        return ProtocolClient(self, token)


def terms(price="1300", **over):
    base = {"bundle_id": "standard", "price": {"amount": price, "currency": "USD"},
            "delivery_days": 21, "payment": {"net_days": 14},
            "late": {"fee_pct": "2", "grace_days": 3}}
    return {**base, **over}
