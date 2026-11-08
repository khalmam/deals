"""A buyer agent that talks to Deals only through its HTTP API, with its own bearer token.
`send(method, path, payload, token)` returns (status, json), so tests can use a Django client
and the command can use httpx. The owner's budget is a hard ceiling; the money steps that need
a human, such as approving the hold on PayPal, are left to the owner."""
from decimal import ROUND_HALF_UP, Decimal

STEPS = (Decimal("0.70"), Decimal("0.78"), Decimal("0.86"), Decimal("0.94"))
WHOLE = Decimal(1)


class BuyerError(Exception):
    pass


def _amount(label):
    return Decimal(label.split()[0]) if label else Decimal(0)


class BuyerAgent:
    def __init__(self, send, token, budget, currency="USD"):
        self.send, self.token = send, token
        self.budget, self.currency = Decimal(str(budget)), currency

    def _call(self, method, path, payload=None, ok=(200, 201)):
        status, body = self.send(method, path, payload, self.token)
        if status not in ok:
            raise BuyerError(f"{method} {path} failed ({status}): {body.get('error', body)}")
        return body

    def find_providers(self, capability=""):
        query = f"?type=PROVIDER&capability={capability}" if capability else "?type=PROVIDER"
        return self._call("GET", f"/api/agents{query}")["results"]

    def shortlist(self, capability=""):
        """Providers that publish a priced bundle, cheapest first. Floors are private, so
        this ranks on list price only; the negotiation finds the real price."""
        ranked = []
        for agent in self.find_providers(capability):
            prices = [Decimal(s["list_price"]) for s in agent["services"]
                      if s.get("list_price") and s.get("currency") == self.currency]
            if prices:
                ranked.append((min(prices), agent["slug"], agent))
        return [a for _, _, a in sorted(ranked, key=lambda r: r[:2])]

    def _say(self, deal_id, text):
        return self._call("POST", f"/api/deals/{deal_id}/offers", {"message": text})

    def _view(self, deal_id):
        return self._call("GET", f"/api/deals/{deal_id}")

    def negotiate(self, provider, bundle, title=""):
        deal = self._call("POST", "/api/deals",
                          {"provider": provider, "bundle": bundle, "title": title})
        deal_id, opening = deal["deal_id"], _amount(deal["ask"])
        goal = min(self.budget, (opening * Decimal("0.90")).quantize(WHOLE, ROUND_HALF_UP))
        log = [f"asked {opening} {self.currency}"]
        for step in STEPS:
            ask = _amount(self._view(deal_id)["ask"])
            if ask <= goal:
                break
            offer = min(self.budget, (opening * step).quantize(WHOLE, ROUND_HALF_UP))
            result = self._say(deal_id, f"I can pay {offer} {self.currency}.")
            log.append(f"offered {offer}: {result['status']}")
            if result["status"] != "COUNTER":
                return self._finish(deal_id, result["status"], log)
        ask = _amount(self._view(deal_id)["ask"])
        if ask > self.budget:
            result = self._say(deal_id, "No thanks, I'm out.")
            return self._finish(deal_id, result["status"], log + ["over budget, walked away"])
        result = self._say(deal_id, "OK, I accept.")
        return self._finish(deal_id, result["status"], log + [f"accepted {ask}"])

    def _finish(self, deal_id, status, log):
        view = self._view(deal_id)
        return {"status": status, "deal_id": deal_id, "price": view["total"],
                "currency": view["currency"], "stage": view["stage"],
                "approve_url": view["approve_url"], "log": log}
