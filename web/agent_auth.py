"""Bearer authentication for agents calling the deal API."""
from functools import wraps

from django.http import JsonResponse

from deals.services.agent_deals import (
    NEGOTIATE_SCOPE,
    AccessDenied,
    AgentDealError,
    check_access,
    start_agent_deal,
)
from deals.services.agent_registry import authenticate_agent
from deals.services.deal_view import DealNotFound, build_deal_view

NEEDS_TOKEN = {"error": "Valid agent credentials with the deals:negotiate scope are required."}


def agent_of(request, scope=NEGOTIATE_SCOPE):
    scheme, _, token = request.headers.get("Authorization", "").partition(" ")
    return authenticate_agent(token.strip(), scope) if scheme.lower() == "bearer" else None


def deal_access(view):
    """Wrap a deal endpoint: agent-owned deals need the owning agent's token."""
    @wraps(view)
    def inner(request, deal_id, *args, **kwargs):
        try:
            check_access(deal_id, agent_of(request))
        except DealNotFound:
            return JsonResponse({"error": "No such deal."}, status=404)
        except AccessDenied as exc:
            return JsonResponse({"error": str(exc)}, status=exc.status)
        return view(request, deal_id, *args, **kwargs)
    return inner


def create_for_agent(request, data):
    """POST /api/deals with a bearer token: the buyer opens a deal with a named provider."""
    agent = agent_of(request)
    if agent is None:
        return JsonResponse(NEEDS_TOKEN, status=401)
    try:
        deal_id = start_agent_deal(agent, str(data.get("provider", "")),
                                   str(data.get("bundle", "")), str(data.get("title", "")))
    except AgentDealError as exc:
        return JsonResponse({"error": str(exc)}, status=exc.status)
    view = build_deal_view(deal_id)
    return JsonResponse({"deal_id": deal_id, "ask": view["ask"], "stage": view["stage"],
                         "url": request.build_absolute_uri(f"/deals/{deal_id}/")}, status=201)
