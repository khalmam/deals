"""Where a deal is, so the page knows what the visitor can do next.

Derived from the deal's state by the table in deals.domain.stage. The ledger is the audit
trail; it is no longer re-scanned (and its entry order no longer decides anything) here."""
from deals.domain.stage import stage_for


def stage_of(deal, entries=None, negotiation_status=None, payout_needs_attention=False):
    """The stage's name. `entries` is accepted for old callers and not needed."""
    return stage_for(deal.state, negotiation_status, payout_needs_attention).name


def next_actions(deal, stage):
    """What can be done next, as plain dicts an agent can follow without reading the page."""
    out = []
    for a in stage.actions:
        href = deal.approve_url if a.path is None else f"/api/deals/{deal.pk}{a.path}"
        if href:
            out.append({"name": a.name, "method": a.method, "href": href})
    return out


def standing_proposal(entries):
    """The latest proposal in an agent-to-agent negotiation, or None."""
    for e in reversed(entries):
        if e.kind == "PROPOSAL_MADE" and e.payload.get("type") in ("PROPOSE", "COUNTER"):
            p = e.payload
            return {"by": p["from"], "type": p["type"], "price": p["price"],
                    "currency": p["currency"]}
    return None


def ask_label(entries):
    for e in reversed(entries):
        if e.kind == "OFFER_MADE" and e.payload.get("by") == "freelancer":
            return f"{e.payload['price']} {e.payload.get('currency', '')}".strip()
    return ""
