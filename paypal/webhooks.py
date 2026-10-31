"""Webhook verification (PayPal's own verify endpoint) and event parsing."""
from deals.domain.ports import WebhookEvent

from .client import PayPalClient


def verify_signature(client: PayPalClient, headers, event, webhook_id):
    h = {k.lower(): v for k, v in headers.items()}
    body = {
        "auth_algo": h.get("paypal-auth-algo"),
        "cert_url": h.get("paypal-cert-url"),
        "transmission_id": h.get("paypal-transmission-id"),
        "transmission_sig": h.get("paypal-transmission-sig"),
        "transmission_time": h.get("paypal-transmission-time"),
        "webhook_id": webhook_id,
        "webhook_event": event,
    }
    d = client.request("POST", "/v1/notification/webhooks/verify-webhook-signature", body)
    return d.get("verification_status") == "SUCCESS"


def parse_event(event):
    res = event.get("resource", {}) or {}
    return WebhookEvent(event["id"], event["event_type"], str(res.get("id", "")), res)
