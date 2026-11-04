"""Where a deal is, read from its ledger, so the page knows what the visitor can do next."""


def stage_of(deal, entries):
    kinds = {e.kind for e in entries}
    if "HOLD_VOIDED" in kinds:
        return "voided"
    if "DEAL_WALKED_AWAY" in kinds:
        return "walked_away"
    if deal.state == "PAID_OUT":
        return "paid"
    for kind, stage in (("CAPTURE_COMPLETED", "captured"), ("DELIVERY_CONFIRMED", "delivered"),
                        ("HOLD_AUTHORIZED", "held"), ("HOLD_REQUESTED", "approval"),
                        ("TERMS_AGREED", "agreed")):
        if kind in kinds:
            return stage
    return "negotiating"


def ask_label(entries):
    for e in reversed(entries):
        if e.kind == "OFFER_MADE" and e.payload.get("by") == "freelancer":
            return f"{e.payload['price']} {e.payload.get('currency', '')}".strip()
    return ""
