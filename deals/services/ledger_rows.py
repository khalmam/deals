"""How a ledger entry is shown on the deal page: its label, colour and one-line summary.
Display only; nothing here reads or writes the database."""


def _when(ts):
    return ts[:19].replace("T", " ") + " UTC" if ts else ""


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
    "PROPOSAL_MADE": ("Proposal", "#0a84ff"),
}


def _summary(kind, p):
    money = f"{p.get('price') or p.get('total') or p.get('amount') or ''} {p.get('currency', '')}"
    if kind in ("OFFER_MADE", "COUNTER_MADE") and p.get("price"):
        return ("Freelancer: " if p.get("by") == "freelancer" else "Client: ") + money.strip()
    if kind == "PROPOSAL_MADE":
        return (f"{p.get('from', '')}: {str(p.get('type', '')).capitalize()} "
                f"{p.get('price', '')} {p.get('currency', '')}").strip()
    if kind == "HOLD_REQUESTED":
        return f"PayPal order {p.get('order_id', '')}".strip()
    if kind == "HOLD_AUTHORIZED":
        return f"PayPal authorization {p.get('auth_id', '')}".strip()
    if kind == "CAPTURE_COMPLETED":
        return f"{money.strip()} · PayPal capture {p.get('capture_id', '')}".strip()
    if kind == "TERMS_AGREED":
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
