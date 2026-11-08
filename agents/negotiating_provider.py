"""A provider agent that runs outside Deals. Its floor lives only in this object: it is never
published, never sent, and never needed by the server."""
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")


@dataclass(frozen=True)
class ProviderPolicy:
    list_price: Decimal
    floor: Decimal  # private to this process
    currency: str = "USD"
    rounds: int = 5
    max_net_days: int = 30
    max_late_fee_pct: Decimal = Decimal("10")


class ExternalProvider:
    def __init__(self, client, slug, policy):
        self.client, self.slug, self.policy = client, slug, policy

    def _level(self, step):
        p = self.policy
        share = Decimal(min(step, p.rounds)) / Decimal(p.rounds)
        return max(p.floor, p.list_price - (p.list_price - p.floor) * share).quantize(
            CENT, ROUND_HALF_UP)

    def _decide(self, view):
        p, head = self.policy, view["head"]
        t = head["terms"]
        offers = sum(1 for m in view["messages"] if m["from"] != self.slug)
        price = Decimal(t["price"]["amount"])
        net = min(t["payment"]["net_days"], p.max_net_days)
        fee = min(Decimal(t["late"]["fee_pct"]), p.max_late_fee_pct)
        if price >= self._level(offers - 1):
            asked = price
        elif offers > p.rounds:
            return {"type": "REJECT"}
        else:
            asked = self._level(offers)
        wanted = {**t, "price": {**t["price"], "amount": str(asked)},
                  "payment": {"net_days": net},
                  "late": {**t["late"], "fee_pct": format(fee.normalize(), "f") if fee else "0"}}
        if asked == price and wanted == t:
            return {"type": "ACCEPT", "terms_hash": head["terms_hash"]}
        return {"type": "COUNTER", "terms": wanted}

    def step(self):
        """Answer every open negotiation where the buyer spoke last.
        Returns [(negotiation_id, reply type), ...]."""
        acted = []
        for item in self.client.inbox():
            if item["status"] != "OPEN" or item["role"] != "provider" or \
                    item["head"]["from"] == self.slug:
                continue
            view = self.client.get(item["negotiation_id"])
            head = view["head"]
            body = {**self._decide(view), "in_reply_to": head["proposal_id"]}
            self.client.answer(item["negotiation_id"], body, f"{self.slug}:{head['proposal_id']}")
            acted.append((item["negotiation_id"], body["type"]))
        return acted
