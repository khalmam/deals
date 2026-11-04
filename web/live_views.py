"""The live flow. The JSON endpoints are the product's API; the pages call them from the
browser. Production use would add authentication; the demo has none."""
import json
import logging

from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from deals.management.live_factory import live_deps as get_deps
from deals.services.deal_view import DealNotFound, build_deal_view
from deals.services.live_deal import (
    LiveError,
    advance,
    approve_return,
    cancel,
    deliver,
    refresh,
    say,
    start_deal,
)

log = logging.getLogger(__name__)


def _run(call):
    try:
        return JsonResponse(call())
    except DealNotFound:
        return JsonResponse({"error": "No such deal."}, status=404)
    except LiveError as exc:
        return JsonResponse({"error": str(exc)}, status=409)
    except Exception as exc:
        log.exception("live step failed")
        return JsonResponse({"error": f"The step failed ({type(exc).__name__}). Try again."},
                            status=502)


def _body(request):
    try:
        data = json.loads(request.body or b"{}")
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _urls(request, deal_id):
    return (request.build_absolute_uri(reverse("hold_return", args=[deal_id])),
            request.build_absolute_uri(reverse("deal", args=[deal_id])))


def start_page(request):
    return render(request, "web/start.html", {"active": "start"})


@csrf_exempt
@require_POST
def api_create(request):
    data = _body(request)
    kwargs = {"title": str(data["title"])[:200]} if data.get("title") else {}
    if data.get("client_email"):
        kwargs["client_email"] = str(data["client_email"])[:200]
    deal_id = start_deal(get_deps(), **kwargs)
    url = request.build_absolute_uri(reverse("deal", args=[deal_id]))
    return JsonResponse({"deal_id": deal_id, "url": url}, status=201)


@require_GET
def api_get(request, deal_id):
    return _run(lambda: build_deal_view(deal_id))


@csrf_exempt
@require_POST
def api_say(request, deal_id):
    text = str(_body(request).get("message", "")).strip()[:500]
    if not text:
        return JsonResponse({"error": "Send a message."}, status=400)
    return _run(lambda: say(get_deps(), str(deal_id), text, _urls(request, deal_id)))


@csrf_exempt
@require_POST
def api_advance(request, deal_id):
    return _run(lambda: advance(get_deps(), str(deal_id), _urls(request, deal_id)))


def _step(fn):
    def view(request, deal_id):
        return _run(lambda: fn(get_deps(), str(deal_id)))
    return csrf_exempt(require_POST(view))


api_delivery = _step(deliver)
api_cancel = _step(cancel)
api_refresh = _step(refresh)


@require_GET
def hold_return(request, deal_id):
    """PayPal sends the buyer here after they approve the hold."""
    try:
        approve_return(get_deps(), str(deal_id))
    except (DealNotFound, LiveError):
        pass  # the deal page shows where things stand either way
    return redirect("deal", deal_id=deal_id)
