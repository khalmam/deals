"""What comes with the freelancer's current ask in a chat negotiation, before anything is
agreed: the deliverables, payment days and late fee. Read-only; it reads the rate card and
builds the terms the way agreement will, so the preview matches what gets locked in."""
from deals.domain.money import Money
from engine.demo_card import demo_card

from .negotiate import build_terms

CLOSED = ("TERMS_AGREED", "DEAL_WALKED_AWAY")


def offer_terms(deal, entries):
    ask = next((e for e in reversed(entries)
                if e.kind == "OFFER_MADE" and e.payload.get("by") == "freelancer"), None)
    if ask is None or any(e.kind in CLOSED for e in entries):
        return None
    try:
        if deal.provider_id:
            from .agent_deals import check_provider  # imported here: agent_deals imports deal_view

            card, _ = check_provider(deal.provider.services, deal.provider.mandate, False)
        else:
            card = demo_card()
        bundle = card.get(ask.payload["bundle"])
        terms = build_terms(bundle, Money.of(ask.payload["price"], ask.payload["currency"]))
    except Exception:  # a preview must never break the deal page
        return None
    return {"deliverables": [{"name": i.get("name", ""), "amount": i.get("amount", "")}
                             for i in terms.get("line_items", [])],
            "net_days": terms.get("net_days", ""), "late_fee_pct": terms.get("late_fee_pct", "")}
