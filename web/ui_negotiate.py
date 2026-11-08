"""The browser path: pick a hosted provider, set your limits, and watch an agent negotiate."""
import json

from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from deals.services.agent_registry import discover_agents
from deals.services.negotiation_views import refresh_view
from deals.services.ui_negotiation import run_for_visitor

from .negotiation_api import after_for
from .ratelimit import limited


def negotiate_page(request):
    providers = [a for a in discover_agents(agent_type="PROVIDER")
                 if a["hosted"] and any(s.get("list_price") for s in a["services"])]
    return render(request, "web/negotiate.html", {"active": "negotiate", "providers": providers})


@csrf_exempt
@require_POST
@limited
def api_ui_negotiate(request):
    try:
        body = json.loads(request.body or b"{}")
        nid = run_for_visitor(str(body.get("provider", "")), str(body.get("bundle", "")),
                              body.get("max_price"), body.get("target_price"),
                              after_for(request))
    except (ValueError, AttributeError) as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    view = refresh_view({"negotiation_id": nid, "created": "", "replayed": False})
    return JsonResponse({"negotiation_id": nid, "status": view["status"],
                         "deal_url": reverse("deal", args=[nid])})
