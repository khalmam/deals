"""One PayPal delivery: check it is really from PayPal, keep the raw event, apply it."""
import json
import logging

from deals.models import WebhookEvent as WebhookRow

from .apply_webhook import apply_webhook

log = logging.getLogger(__name__)


class BadWebhook(Exception):
    """Not JSON, not an event, or not signed by PayPal. Nothing was stored or applied."""


def receive_webhook(headers, body, gateway, now=None):
    """gateway.verify(headers, raw) -> bool and gateway.parse(raw) -> WebhookEvent.
    Returns what apply_webhook returned. If applying fails, the raw event is logged and the
    error is raised, so the caller answers 5xx and PayPal sends the event again."""
    try:
        raw = json.loads(body)
    except ValueError as exc:
        raise BadWebhook("body is not JSON") from exc
    if not isinstance(raw, dict):
        raise BadWebhook("body is not an event")
    if not gateway.verify(headers, raw):
        raise BadWebhook("signature check failed")
    try:
        event = gateway.parse(raw)
    except (KeyError, TypeError) as exc:
        raise BadWebhook("event has no id or type") from exc
    try:
        result = apply_webhook(event, now)
    except Exception:
        log.exception("webhook %s could not be applied; raw event: %s", event.event_id, raw)
        raise
    if result != "DUPLICATE":
        WebhookRow.objects.filter(event_id=event.event_id).update(payload=raw)
    return result
