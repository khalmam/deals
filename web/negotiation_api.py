"""HTTP face of the negotiation protocol. Hosted and external providers use these same routes."""
import json
import re

from django.http import JsonResponse
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from deals.domain.proposal import ProposalError
from deals.management.live_factory import live_deps as get_deps
from deals.services.agent_deals import for_deal
from deals.services.negotiation_after import after_message
from deals.services.negotiation_protocol import open_negotiation, submit_message
from deals.services.negotiation_rules import NegotiationError
from deals.services.negotiation_verify import verify_negotiation
from deals.services.negotiation_views import list_negotiations, party_view

from .agent_auth import NEEDS_TOKEN, agent_of

KEY = re.compile(r"^[A-Za-z0-9._:-]{8,80}$")


def _error(message, code, status, **extra):
    return JsonResponse({"error": message, "code": code, **extra}, status=status)


def _json(request):
    try:
        data = json.loads(request.body or b"{}")
    except ValueError:
        raise ProposalError("the body must be JSON", "BAD_JSON") from None
    if not isinstance(data, dict):
        raise ProposalError("the body must be a JSON object", "BAD_JSON")
    return data


def _call(request, work):
    """Authenticate, parse, run `work(agent, body, key)` and turn refusals into JSON."""
    agent = agent_of(request)
    if agent is None:
        return JsonResponse(NEEDS_TOKEN, status=401)
    try:
        key = request.headers.get("Idempotency-Key", "")
        if not KEY.match(key):
            raise ProposalError("send an Idempotency-Key header of 8 to 80 characters "
                                "(letters, digits . _ : -)", "IDEMPOTENCY_KEY_REQUIRED")
        return work(agent, _json(request), key)
    except NegotiationError as exc:
        return _error(str(exc), exc.code, exc.status, **exc.extra)
    except ProposalError as exc:
        return _error(str(exc), exc.code, 400)


def after_for(request):
    """The follow-up step for this request: hosted answers, then the PayPal hold."""
    def urls_for(nid):
        return (request.build_absolute_uri(reverse("hold_return", args=[nid])),
                request.build_absolute_uri(reverse("deal", args=[nid])))
    return lambda view: after_message(view, urls_for, lambda nid: for_deal(get_deps(), nid))


@csrf_exempt
@require_http_methods(["GET", "POST"])
def api_negotiations(request):
    if request.method == "GET":
        agent = agent_of(request)
        if agent is None:
            return JsonResponse(NEEDS_TOKEN, status=401)
        return JsonResponse({"results": list_negotiations(agent)})

    def work(agent, body, key):
        view = after_for(request)(open_negotiation(agent, str(body.get("provider", "")),
                                                body.get("terms"), key, body))
        return JsonResponse(view, status=200 if view["replayed"] else 201)
    return _call(request, work)


@csrf_exempt
@require_http_methods(["POST"])
def api_negotiation_messages(request, negotiation_id):
    def work(agent, body, key):
        return JsonResponse(after_for(request)(submit_message(agent, negotiation_id, body, key)))
    return _call(request, work)


@require_http_methods(["GET"])
def api_negotiation(request, negotiation_id):
    agent = agent_of(request)
    if agent is None:
        return JsonResponse(NEEDS_TOKEN, status=401)
    try:
        body = party_view(agent, negotiation_id)
        if request.GET.get("verify"):
            body["verification"] = verify_negotiation(negotiation_id)
    except NegotiationError as exc:
        return _error(str(exc), exc.code, exc.status)
    return JsonResponse(body)
