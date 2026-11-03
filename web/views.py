from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from deals.management.paypal_factory import webhook_gateway_from_settings as get_gateway
from deals.services.receive_webhook import BadWebhook, receive_webhook


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
