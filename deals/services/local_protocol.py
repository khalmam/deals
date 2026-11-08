"""An in-process stand-in for the HTTP transport: the same routes, answered by calling the
protocol services directly. A hosted agent uses it, so it speaks exactly the protocol an
external agent would, through the same validation."""
import re

from deals.domain.proposal import ProposalError

from .agent_registry import get_agent
from .negotiation_protocol import open_negotiation, submit_message
from .negotiation_rules import NegotiationError
from .negotiation_verify import verify_negotiation
from .negotiation_views import party_view

ID = r"([0-9a-f-]{36})"


def local_send(agent, after):
    """send(method, path, payload, token, headers) for `agent`; `after` finishes each write."""
    def send(method, path, payload, token, headers=None):
        key = (headers or {}).get("Idempotency-Key", "")
        route, _, query = path.partition("?")
        try:
            if route == "/api/agents/me":
                return 200, {"slug": agent.slug}
            if m := re.fullmatch(r"/api/agents/([\w-]+)", route):
                found = get_agent(m[1])
                return (200, found) if found else (404, {"error": "No such agent."})
            if method == "POST" and route == "/api/negotiations":
                return 201, after(open_negotiation(agent, str(payload.get("provider", "")),
                                                   payload.get("terms"), key, payload))
            if m := re.fullmatch(rf"/api/negotiations/{ID}/messages", route):
                return 200, after(submit_message(agent, m[1], payload, key))
            if m := re.fullmatch(rf"/api/negotiations/{ID}", route):
                body = party_view(agent, m[1])
                if "verify" in query:
                    body["verification"] = verify_negotiation(m[1])
                return 200, body
        except NegotiationError as exc:
            return exc.status, {"error": str(exc), "code": exc.code, **exc.extra}
        except ProposalError as exc:
            return 400, {"error": str(exc), "code": exc.code}
        return 404, {"error": "no such route"}
    return send
