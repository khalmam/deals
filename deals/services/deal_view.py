"""Read model for the deal page: one deal as plain dicts and strings, so the web layer never
touches a model. Everything here comes from the deal row and its ledger."""
from deals.domain.payout import summarise
from deals.domain.stage import stage_for
from deals.models import Deal, Negotiation
from deals.domain.payout import summarise
from deals.domain.stage import stage_for
from deals.models import Deal, Negotiation

from .chat_log import merge_chat
from .deal_stage import ask_label, next_actions, standing_proposal
from .ledger import verify_ledger

TIMELINE = (
    ("DEAL_OPENED", "Deal opened"),
    ("TERMS_AGREED", "Terms agreed"),
    ("HOLD_REQUESTED", "Hold requested"),
    ("HOLD_AUTHORIZED", "Hold approved"),
    ("DELIVERY_CONFIRMED", "Delivery confirmed"),
    ("CAPTURE_COMPLETED", "Payment captured"),
    ("PAYOUT_SENT", "Payouts sent"),
    ("PAYOUT_ITEM_SUCCEEDED", "Payouts confirmed"),
)
END_STEPS = {"HOLD_VOIDED": "Hold voided", "DEAL_WALKED_AWAY": "Walked away"}
SOURCES = {"model": "the model", "engine": "the rules engine", "rate_card": "the rate card"}


class DealNotFound(Exception):
    pass


def _when(ts):
    return ts[:19].replace("T", " ") + " UTC" if ts else ""


def _timeline(entries):
    first, last_ok = {}, None
    for e in entries:
        first.setdefault(e.kind, e)
        if e.kind == "PAYOUT_ITEM_SUCCEEDED":
            last_ok = e
    sent = first.get("PAYOUT_SENT")
    expected = len(sent.payload.get("items", [])) if sent else 0
    confirmed = sum(1 for e in entries if e.kind == "PAYOUT_ITEM_SUCCEEDED")
    steps = []
    for kind, label in TIMELINE:
        e = first.get(kind)
        if kind == "PAYOUT_ITEM_SUCCEEDED":
            e = last_ok if expected and confirmed >= expected else None
        steps.append({"label": label, "done": e is not None, "current": False,
                      "time": _when(e.ts) if e else ""})
    for kind, label in END_STEPS.items():
        if kind in first:  # a branch that ended the deal: show only what happened
            steps = [s for s in steps if s["done"]]
            steps.append({"label": label, "done": True, "current": False,
                          "time": _when(first[kind].ts)})
            return steps
    done = [i for i, s in enumerate(steps) if s["done"]]
    if done:
        steps[done[-1]]["current"] = True
    return steps


def _transcript(entries):
    rows = []
    for e in entries:
        p = e.payload
        if e.kind == "DEAL_WALKED_AWAY" and p.get("by") == "freelancer":
            rows.append({"who": "Freelancer", "price": "", "currency": "", "source": "",
                         "message": p.get("reason", ""), "walked_away": True, "notes": []})
        if e.kind == "PROPOSAL_MADE":
            rows.append({"who": p["from"], "price": p["price"], "currency": p["currency"],
                         "message": p["type"].capitalize(), "source": "agent protocol",
                         "walked_away": p["type"] in ("REJECT", "WITHDRAW"), "notes": []})
            continue
        if e.kind not in ("OFFER_MADE", "COUNTER_MADE"):
            continue
        src = p.get("source", "")
        rows.append({"who": "Freelancer" if p.get("by") == "freelancer" else "Client",
                     "price": p.get("price", ""), "currency": p.get("currency", ""),
                     "message": p.get("message", ""), "walked_away": p.get("action") == "WALK_AWAY",
                     "source": SOURCES.get(src, src), "notes": list(p.get("notes", []))})
    return rows


def _talk(deal, entries):
    rows = []
    for e in entries:  # tag each row with its entry's seq so chat can be slotted in
        rows += [dict(r, seq=e.seq) for r in _transcript([e])]
    return merge_chat(rows, deal)


def _terms(deal):
    t = deal.terms or {}
    return {"bundle": t.get("bundle_name", ""), "list_price": t.get("list_price", ""),
            "freelancer_net": t.get("freelancer_net", ""), "net_days": t.get("net_days", ""),
            "late_fee_pct": t.get("late_fee_pct", ""), "line_items": t.get("line_items", []),
            "payouts": t.get("payouts", []), "hash": deal.terms_hash}


def _actions(entries):
    rows = []
    for e in entries:
        if e.kind != "AGENT_ACTION":
            continue
        p, ok = e.payload, bool(e.payload.get("ok"))
        rows.append({"time": _when(e.ts), "ok": ok,
                     "tool": str(p.get("tool", "")).replace("_", " ").capitalize(),
                     "result": "Done" if ok else "Refused: " + str(p.get("error", "")),
                     "decided_by": str(p.get("source", "")).capitalize(),
                     "why": p.get("why", "")})
    return rows


KINDS = {
    "DEAL_OPENED": ("Deal opened", "#8e8e93"), "MANDATE_SET": ("Mandate set", "#8e8e93"),
    "OFFER_MADE": ("Offer made", "#0a84ff"), "COUNTER_MADE": ("Counter-offer", "#0a84ff"),
    "TERMS_AGREED": ("Terms agreed", "#8e5cf7"), "HOLD_REQUESTED": ("Hold requested", "#ff9f0a"),
    "HOLD_AUTHORIZED": ("Hold approved", "#ff9f0a"),
    "DELIVERY_CONFIRMED": ("Delivery confirmed", "#30a46c"),
    "CAPTURE_COMPLETED": ("Payment captured", "#30a46c"),
    "PAYOUT_SENT": ("Payouts sent", "#30a46c"),
    "PAYOUT_ITEM_SUCCEEDED": ("Payout confirmed", "#30a46c"),
    "WEBHOOK_APPLIED": ("PayPal update", "#8e8e93"), "AGENT_ACTION": ("Agent action", "#d6409f"),
    "HOLD_VOIDED": ("Hold voided", "#d9453d"), "DEAL_WALKED_AWAY": ("Walked away", "#d9453d"),
}


def _summary(kind, p):
    money = f"{p.get('price') or p.get('total') or p.get('amount') or ''} {p.get('currency', '')}"
    if kind in ("OFFER_MADE", "COUNTER_MADE") and p.get("price"):
        return ("Freelancer: " if p.get("by") == "freelancer" else "Client: ") + money.strip()
    if kind in ("TERMS_AGREED", "CAPTURE_COMPLETED"):
        return money.strip()
    if kind == "AGENT_ACTION":
        tool = str(p.get("tool", "")).replace("_", " ")
        return f"{tool} · {'done' if p.get('ok') else 'refused'} · {p.get('source', '')}"
    return ""


def _ledger(entries, verified):
    broken = None if not verified or verified["intact"] else verified["broken_seq"]
    rows = []
    for pos, e in enumerate(entries, 1):
        label, color = KINDS.get(e.kind, (e.kind.replace("_", " ").capitalize(), "#8e8e93"))
        state = "ok" if not broken or pos < broken else ("bad" if pos == broken else "unverified")
        rows.append({"seq": e.seq, "kind": e.kind, "label": label, "color": color,
                     "summary": _summary(e.kind, e.payload), "state": state, "first": pos == 1,
                     "date": e.ts[:10], "time": _when(e.ts), "hash": e.hash,
                     "short_hash": e.hash[:8], "prev_short": e.prev_hash[:8]})
    return rows


def build_deal_view(deal_id, verify=False):
    """Return the whole deal page as plain data. verify=True also re-checks the hash chain."""
    deal = Deal.objects.filter(pk=deal_id).first()
    if deal is None:
        raise DealNotFound(str(deal_id))
    entries = list(deal.ledger.order_by("seq"))
    verified = None
    if verify:
        bad = verify_ledger(deal)
        verified = {"intact": bad is None, "broken_seq": None if bad is None else bad + 1,
                    "checked": len(entries)}
    neg = Negotiation.objects.filter(pk=deal.pk).values_list("status", flat=True).first()
    payouts = summarise(deal.payments.filter(kind="PAYOUT_ITEM").values_list("status", flat=True))
    stage = stage_for(deal.state, neg, payouts["needs_attention"])
    neg = Negotiation.objects.filter(pk=deal.pk).values_list("status", flat=True).first()
    payouts = summarise(deal.payments.filter(kind="PAYOUT_ITEM").values_list("status", flat=True))
    stage = stage_for(deal.state, neg, payouts["needs_attention"])
    return {
        "stage": stage.name, "waiting_on": stage.waiting_on, "next": next_actions(deal, stage),
        "payouts": payouts, "standing": standing_proposal(entries),
        "approve_url": deal.approve_url, "ask": ask_label(entries),
        "proof": _proof(entries),
        "id": str(deal.pk), "short_id": str(deal.pk)[:8], "title": deal.title,
        "client_email": deal.client_email, "state": deal.state,
        "state_label": deal.state.replace("_", " ").capitalize(),
        "total": "" if deal.total_amount is None else str(deal.total_amount),
        "currency": deal.currency, "terms": _terms(deal),
        "timeline": _timeline(entries), "transcript": _talk(deal, entries),
        "actions": _actions(entries),
        "ledger": _ledger(entries, verified),
        "head_hash": entries[-1].hash if entries else "", "verified": verified,
    }


def _proof(entries):
    acts = _actions(entries)
    return {"actions": len(acts), "model": sum(a["decided_by"] == "Model" for a in acts),
            "entries": len(entries)}
