"""Read-only panels for the deal page: who is in the deal, what is proposed, where the PayPal
payment stands, and one timeline of everything. Nothing here writes to the database, talks to
PayPal or moves money; it only reads what the deal and its ledger already hold."""
from datetime import timezone as _utc

from deals.models import Negotiation

WAITING = {"client": "The client", "agents": "The two agents", "agent": "The deal agent",
           "paypal": "PayPal", "owner": "The deal owner", "nobody": "Nobody: the deal is finished"}

HEADLINE = {
    "DRAFT": ("Not started", "No payment has been requested. PayPal is involved once both "
                             "sides agree on terms."),
    "NEGOTIATING": ("Not started", "No payment has been requested. PayPal is involved once "
                                   "both sides agree on terms."),
    "WALKED_AWAY": ("No payment", "The negotiation ended without an agreement, so PayPal was "
                                  "never asked to hold anything."),
    "AGREED": ("Ready to request authorization", "The terms are agreed. The agent now asks "
                                                 "PayPal to authorize the payment."),
    "HOLD_PENDING": ("Waiting for approval on PayPal", "PayPal created an order for the agreed "
                     "amount. Approve it with your PayPal account to authorize the payment. "
                     "Nothing is captured yet."),
    "HOLD_ACTIVE": ("Payment authorized by PayPal", "PayPal has authorized the agreed amount. "
                    "It is captured only after the client confirms delivery."),
    "DELIVERED": ("Delivery confirmed", "The next step is capturing the authorized payment."),
    "CAPTURED": ("Payment captured", "PayPal has captured the payment. Sub-contractor payouts "
                 "are being confirmed."),
    "PAID_OUT": ("Completed", "The payment was captured and every payout is settled."),
    "INVOICED": ("Completed", "The payment was captured. An invoice for the balance is out."),
    "CLOSED": ("Completed", "The payment was captured and the deal is closed."),
    "VOIDED": ("Authorization voided", "The authorization was released, so the payment was "
               "never captured."),
}
NOTE = ("Every PayPal step runs through the Deals backend, and only when the deal state and the "
        "owner’s mandate allow it. Capture is possible only after the client confirms delivery. "
        "This runs on PayPal’s sandbox, so no real money moves.")
SOURCE = {"HOLD_REQUESTED": "PayPal", "HOLD_AUTHORIZED": "PayPal", "CAPTURE_COMPLETED": "PayPal",
          "HOLD_VOIDED": "PayPal", "PAYOUT_SENT": "PayPal", "PAYOUT_ITEM_SUCCEEDED": "PayPal",
          "WEBHOOK_APPLIED": "PayPal", "OFFER_MADE": "Negotiation", "COUNTER_MADE": "Negotiation",
          "PROPOSAL_MADE": "Negotiation", "TERMS_AGREED": "Negotiation", "AGENT_ACTION": "Agent"}


def _when(ts):
    return ts[:19].replace("T", " ") + " UTC" if ts else ""


def parties_panel(deal, waiting_on):
    client = f"{deal.buyer.name} (buyer agent)" if deal.buyer_id else deal.client_email
    provider = (f"{deal.provider.name} (provider agent)" if deal.provider_id
                else "The freelancer’s agent")
    return {"client": client, "provider": provider, "next": WAITING.get(waiting_on, "")}


def _protocol_proposal(deal, neg):
    msgs = list(neg.messages.select_related("sender").order_by("version"))
    head = next((m for m in reversed(msgs) if m.msg_type in ("PROPOSE", "COUNTER")), None)
    if head is None:
        return None
    t = head.terms or {}
    price, pay, late = t.get("price") or {}, t.get("payment") or {}, t.get("late") or {}
    rows = [{"label": "Package", "value": t.get("bundle_id", "")}]
    if t.get("delivery_days") is not None:
        rows.append({"label": "Delivery", "value": f"{t['delivery_days']} days"})
    if pay.get("net_days") is not None:
        rows.append({"label": "Payment", "value": f"Net {pay['net_days']} days"})
    if late.get("fee_pct") is not None:
        rows.append({"label": "Late fee",
                     "value": f"{late['fee_pct']}% after {late.get('grace_days', 0)} days"})
    agreed_by = {m.sender_id for m in msgs
                 if m.msg_type == "ACCEPT" and m.terms_hash == head.terms_hash} | {head.sender_id}
    both = neg.status == "AGREED"
    return {"kind": "Proposal" if head.msg_type == "PROPOSE" else "Counter-proposal",
            "by": head.sender.name, "version": head.version,
            "price": f"{price.get('amount', '')} {price.get('currency', '')}".strip(),
            "rows": rows, "status": neg.status.capitalize(),
            "buyer_agreed": both or deal.buyer_id in agreed_by,
            "provider_agreed": both or deal.provider_id in agreed_by}


def _browser_proposal(deal, entries):
    ask = next((e for e in reversed(entries)
                if e.kind == "OFFER_MADE" and e.payload.get("by") == "freelancer"), None)
    if ask is None:
        return None
    kinds = {e.kind for e in entries}
    agreed = "TERMS_AGREED" in kinds
    p = ask.payload
    price = (f"{deal.total_amount} {deal.currency}" if agreed and deal.total_amount is not None
             else f"{p.get('price', '')} {p.get('currency', '')}".strip())
    status = "Agreed" if agreed else ("Ended" if "DEAL_WALKED_AWAY" in kinds else "Open")
    return {"kind": "Agreed price" if agreed else "Current ask", "by": "The freelancer’s agent",
            "version": "", "price": price,
            "rows": [{"label": "Package", "value": p.get("bundle", "")}], "status": status,
            "buyer_agreed": agreed, "provider_agreed": agreed}


def proposal_panel(deal, entries):
    """The standing proposal and who has agreed to it, from whichever negotiation the deal had."""
    neg = Negotiation.objects.filter(pk=deal.pk).first()
    return _protocol_proposal(deal, neg) if neg is not None else _browser_proposal(deal, entries)


def paypal_panel(deal, entries, payouts):
    first, last_ok = {}, None
    for e in entries:
        first.setdefault(e.kind, e)
        if e.kind == "PAYOUT_ITEM_SUCCEEDED":
            last_ok = e
    capture = deal.payments.filter(kind="CAPTURE").first()
    finished = deal.state in ("PAID_OUT", "INVOICED", "CLOSED")

    def step(label, kind, detail=""):
        e = first.get(kind)
        return {"label": label, "done": e is not None, "current": False,
                "time": _when(e.ts) if e else "", "detail": detail if e else ""}

    expires = deal.authorization_expires[:10] if deal.authorization_expires else ""
    steps = [
        step("Authorization requested", "HOLD_REQUESTED",
             f"Order {deal.order_id}" if deal.order_id else ""),
        step("Approved on PayPal", "HOLD_AUTHORIZED", f"Expires {expires}" if expires else ""),
        step("Delivery confirmed", "DELIVERY_CONFIRMED"),
        step("Payment captured", "CAPTURE_COMPLETED",
             f"Capture {capture.paypal_id}" if capture else ""),
    ]
    sent = first.get("PAYOUT_SENT")
    if payouts["total"]:
        detail = f"{payouts['done']} of {payouts['total']} confirmed by PayPal"
    else:
        detail = "No sub-contractor payouts due" if sent else ""
    paid_at = last_ok or sent
    steps.append({"label": "Payouts complete", "done": finished, "current": False,
                  "time": _when(paid_at.ts) if finished and paid_at else "",
                  "detail": detail if (sent or finished) else ""})
    if "HOLD_VOIDED" in first:
        steps = [s for s in steps if s["done"]]
        steps.append({"label": "Authorization voided", "done": True, "current": False,
                      "time": _when(first["HOLD_VOIDED"].ts), "detail": "Never captured"})
    done = [i for i, s in enumerate(steps) if s["done"]]
    if done:
        steps[done[-1]]["current"] = True
    headline, explain = HEADLINE.get(deal.state, ("", ""))
    if deal.state == "CAPTURED" and payouts["needs_attention"]:
        explain = ("PayPal captured the payment, but reports a problem with a sub-contractor "
                   "payout. Use Refresh from PayPal, then check the PayPal activity page.")
    ids = []
    if deal.order_id:
        ids.append({"label": "PayPal order", "value": deal.order_id})
    if deal.auth_id:
        ids.append({"label": "Authorization", "value": deal.auth_id})
    if capture:
        ids.append({"label": "Capture", "value": capture.paypal_id})
    return {"headline": headline, "explain": explain, "steps": steps, "ids": ids, "note": NOTE}


def activity_panel(ledger, deal):
    """One timeline: ledger entries and small-talk chat, in order. The two stay separate in the
    database; this only lays them side by side for reading."""
    rows = [{"label": r["label"], "color": r["color"], "summary": r["summary"], "time": r["time"],
             "source": SOURCE.get(r["kind"], "Deals"), "seq": r["seq"], "order": 0}
            for r in ledger]
    for m in deal.chat.all():
        ts = m.created_at
        if ts.tzinfo is not None:
            ts = ts.astimezone(_utc.utc)
        rows.append({"label": ("Client" if m.who == "client" else "Freelancer") + " message",
                     "color": "#8e8e93", "summary": m.text, "source": "Chat",
                     "time": ts.strftime("%Y-%m-%d %H:%M:%S") + " UTC",
                     "seq": m.after_seq, "order": 1})
    rows.sort(key=lambda r: (r["seq"], r["order"]))
    return rows
