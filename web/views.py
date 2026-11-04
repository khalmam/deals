from django.http import Http404, JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from deals.management.paypal_factory import webhook_gateway_from_settings as get_gateway
from deals.services.deal_view import DealNotFound, build_deal_view
from deals.services.receive_webhook import BadWebhook, receive_webhook
from deals.services.site_view import activity_feed, build_receipt_view, list_deals, site_summary


def health(request):
    return JsonResponse({"status": "up"})


@csrf_exempt
@require_POST
def paypal_webhook(request):
    """PayPal retries anything that is not 2xx. A bad signature is a 400 (nothing is stored);
    an unknown or already-handled event is a 200, so PayPal stops sending it."""
    try:
        result = receive_webhook(request.headers, request.body, get_gateway())
    except BadWebhook as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    return JsonResponse({"result": result})


def deal_page(request, deal_id):
    try:
        deal = build_deal_view(deal_id, verify=True)
    except DealNotFound:
        raise Http404("No such deal") from None
    return render(request, "web/deal.html", {"deal": deal})


def home(request):
    return render(request, "web/home.html", {"active": "home", "site": site_summary()})


def deal_list(request):
    return render(request, "web/deals.html", {"active": "deals", "deals": list_deals()})


def receipt_page(request, deal_id):
    try:
        receipt = build_receipt_view(deal_id)
    except DealNotFound:
        raise Http404("No such deal") from None
    return render(request, "web/receipt.html", {"active": "deals", "r": receipt})


def activity(request):
    return render(request, "web/activity.html", {"active": "activity", "events": activity_feed()})
