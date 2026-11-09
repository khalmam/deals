"""Read models for the home, deals, receipt and activity pages: plain dicts and strings only."""
from deals.domain.payout import stored_status
from deals.models import Deal, LedgerEntry, WebhookEvent

from .deal_view import DealNotFound
from .seal import build_receipt

STAMP = "%Y-%m-%d %H:%M UTC"
EVENT_LABELS = {"applied": "Applied", "ignored": "Ignored: not a payout event",
                "unapplied": "Not applied yet: no matching payout, or awaiting a retry"}


def _label(state):
    return state.replace("_", " ").capitalize()


def list_deals():
    return [{"id": str(d.pk), "short_id": str(d.pk)[:8], "title": d.title,
             "client_email": d.client_email, "state_label": _label(d.state),
             "total": "" if d.total_amount is None else str(d.total_amount),
             "currency": d.currency, "opened": d.created_at.strftime(STAMP)}
            for d in Deal.objects.order_by("-created_at")]


def showcase_deal_id():
    """The deal the home page points at: the newest fully paid one, else the newest."""
    deal = (Deal.objects.filter(state="PAID_OUT").order_by("-created_at").first()
            or Deal.objects.order_by("-created_at").first())
    return str(deal.pk) if deal else ""


def site_summary():
    return {"deals": Deal.objects.count(),
            "paid_out": Deal.objects.filter(state="PAID_OUT").count(),
            "entries": LedgerEntry.objects.count(), "showcase": showcase_deal_id()}


def build_receipt_view(deal_id):
    deal = Deal.objects.filter(pk=deal_id).first()
    if deal is None:
        raise DealNotFound(str(deal_id))
    r = build_receipt(deal)
    r["short_id"], r["state_label"] = r["deal_id"][:8], _label(r["state"])
    r["entries"] = [{**e, "short_hash": e["hash"][:12]} for e in r["entries"]]
    return r


def activity_feed(limit=50):
    out = []
    for w in WebhookEvent.objects.order_by("-received_at")[:limit]:
        status = stored_status(w.event_type, w.applied)
        out.append({"received": w.received_at.strftime(STAMP), "type": w.event_type,
                    "resource": w.resource_id, "applied": w.applied, "status": status,
                    "status_label": EVENT_LABELS[status]})
    return out
