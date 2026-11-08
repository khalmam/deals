"""A procurement agent. It decides for itself, against its owner's limits, what to propose,
whether a counteroffer is acceptable, and when to walk away. Deals only relays and records."""
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

WHOLE = Decimal(1)


@dataclass(frozen=True)
class BuyerPolicy:
    max_price: Decimal  # the hard ceiling, never exceeded
    target_price: Decimal  # accepted at once when everything else is acceptable
    max_delivery_days: int
    min_net_days: int
    max_late_fee_pct: Decimal
    currency: str = "USD"
    rounds: int = 5
    opening_share: Decimal = Decimal("0.70")  # of the provider's published list price


def _round(value):
    return value.quantize(WHOLE, ROUND_HALF_UP)


class ProcurementAgent:
    def __init__(self, client, slug, policy):
        self.client, self.slug, self.policy = client, slug, policy
        self.negotiation_id = None

    def _terms(self, bundle_id, price, delivery, net_days, fee):
        return {"bundle_id": bundle_id, "price": {"amount": str(price), "currency":
                                                  self.policy.currency},
                "delivery_days": delivery, "payment": {"net_days": net_days},
                "late": {"fee_pct": str(fee)}}

    def start(self, provider_slug, bundle_id):
        p = self.policy
        bundle = next(s for s in self.client.provider(provider_slug)["services"]
                      if s.get("id") == bundle_id)
        price = min(p.max_price, _round(Decimal(bundle["list_price"]) * p.opening_share))
        terms = self._terms(bundle_id, price, p.max_delivery_days, p.min_net_days, 0)
        view = self.client.open(provider_slug, terms, f"{self.slug}:open:{provider_slug}:"
                                f"{bundle_id}:{price}")
        self.negotiation_id = view["negotiation_id"]
        return view

    def _decide(self, view):
        p, head = self.policy, view["head"]
        t = head["terms"]
        price, fee = Decimal(t["price"]["amount"]), Decimal(t["late"]["fee_pct"])
        mine = [m for m in view["messages"] if m["from"] == self.slug]
        if not mine:
            raise RuntimeError(f"this negotiation was not opened by {self.slug}")
        used, last = len(mine), Decimal(mine[-1]["terms"]["price"]["amount"])
        fine = (t["delivery_days"] <= p.max_delivery_days and t["payment"]["net_days"]
                >= p.min_net_days and fee <= p.max_late_fee_pct)
        gap = price - last
        nxt = min(p.max_price, last + (max(WHOLE, _round(gap * Decimal("0.25"))) if gap > 0
                                       else WHOLE))
        if fine and (price <= p.target_price or price <= last or price <= nxt):
            return {"type": "ACCEPT", "terms_hash": head["terms_hash"]}
        if used >= p.rounds or (last >= p.max_price and price > p.max_price):
            return {"type": "REJECT"}
        return {"type": "COUNTER", "terms": self._terms(
            t["bundle_id"], nxt, min(t["delivery_days"], p.max_delivery_days),
            max(t["payment"]["net_days"], p.min_net_days), min(fee, p.max_late_fee_pct))}

    def step(self):
        """Act once if it is our turn. Returns 'done', 'waiting' or 'acted'."""
        view = self.client.get(self.negotiation_id)
        if view["status"] != "OPEN":
            return "done"
        head = view["head"]
        if head["from"] == self.slug:
            return "waiting"
        body = {**self._decide(view), "in_reply_to": head["proposal_id"]}
        self.client.answer(self.negotiation_id, body, f"{self.slug}:{head['proposal_id']}")
        return "acted"
