"""Webhook verification (PayPal's own verify endpoint) and event parsing."""
import logging

from deals.domain.ports import WebhookEvent

from .client import PayPalClient

log = logging.getLogger(__name__)


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
    d = client.request("POST", "/v1/notifications/verify-webhook-signature", body)
    status = d.get("verification_status")
    if status != "SUCCESS":
        # Say why a delivery was refused: what PayPal answered and which headers were missing.
        needed = ("paypal-auth-algo", "paypal-cert-url", "paypal-transmission-id",
                  "paypal-transmission-sig", "paypal-transmission-time")
        missing = [k for k in needed if not h.get(k)]
        log.warning("webhook verify: PayPal answered %s for %s (missing headers: %s, webhook id ends %s)",
                    status, h.get("paypal-transmission-id"), missing or "none", str(webhook_id)[-4:])
    return status == "SUCCESS"


def parse_event(event):
    res = event.get("resource", {}) or {}
    # Most resources carry "id"; a payout item event carries "payout_item_id" instead.
    rid = res.get("id") or res.get("payout_item_id") or ""
    return WebhookEvent(event["id"], event["event_type"], str(rid), res)


class WebhookGateway:
    """What the web layer needs from PayPal for webhooks: verify a delivery, parse an event."""

    def __init__(self, client: PayPalClient, webhook_id):
        if not webhook_id:
            raise ValueError("PAYPAL_WEBHOOK_ID is not set")
        self._client, self._webhook_id = client, webhook_id

    def verify(self, headers, raw_event):
        from .client import PayPalError
        try:
            return verify_signature(self._client, headers, raw_event, self._webhook_id)
        except PayPalError as exc:  # PayPal could not verify it: junk or foreign request
            log.warning("webhook verify: PayPal rejected the verification call: %s", exc)
            return False

    def parse(self, raw_event):
        return parse_event(raw_event)
