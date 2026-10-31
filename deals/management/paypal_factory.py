from django.conf import settings

from paypal import PayPalClient, PayPalConfig, PayPalPayments


def payments_from_settings():
    cfg = PayPalConfig(settings.PAYPAL_CLIENT_ID, settings.PAYPAL_CLIENT_SECRET,
                       settings.PAYPAL_BASE_URL, settings.PAYPAL_WEBHOOK_ID)
    return PayPalPayments(PayPalClient(cfg))
