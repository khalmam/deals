from functools import lru_cache

from django.conf import settings

from paypal import PayPalClient, PayPalConfig, PayPalPayments, WebhookGateway


def _config():
    return PayPalConfig(settings.PAYPAL_CLIENT_ID, settings.PAYPAL_CLIENT_SECRET,
                        settings.PAYPAL_BASE_URL, settings.PAYPAL_WEBHOOK_ID)


def payments_from_settings():
    return PayPalPayments(PayPalClient(_config()))


@lru_cache(maxsize=1)
def webhook_gateway_from_settings():
    """One shared client, so the access token is reused between deliveries."""
    return WebhookGateway(PayPalClient(_config()), settings.PAYPAL_WEBHOOK_ID)
