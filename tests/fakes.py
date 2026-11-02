"""In-memory stand-in for PayPal, used by unit tests only (never by the demo)."""
from deals.domain.ports import Authorization, Capture, HoldRequest, PayoutResult


class FakePayments:
    def __init__(self, tamper_custom_id=False):
        self.calls = []
        self.payouts = []
        self.payout_status = "SUCCESS"
        self.tamper = tamper_custom_id
        self._hold = None

    def create_hold(self, deal_ref, amount, terms_hash, return_url, cancel_url):
        self.calls.append(("create_hold", deal_ref))
        self._hold = (amount, terms_hash)
        return HoldRequest("ORDER-1", "https://sandbox.example/approve/ORDER-1")

    def authorize(self, deal_ref, order_id):
        self.calls.append(("authorize", deal_ref))
        return self.get_authorization("AUTH-1")

    def get_authorization(self, auth_id):
        amount, h = self._hold
        return Authorization(auth_id, "2026-11-27T00:00:00Z", amount,
                             "tampered" if self.tamper else h)

    def capture(self, deal_ref, auth_id, amount, final, step):
        self.calls.append(("capture", deal_ref, step))
        return Capture("CAP-1", "COMPLETED", amount)

    def void(self, deal_ref, auth_id):
        self.calls.append(("void", deal_ref))

    def refund(self, deal_ref, capture_id, amount, step):
        return "REF-1"

    def send_payout(self, batch_key, items):
        self.calls.append(("send_payout", batch_key))
        self.payouts.append(list(items))
        return PayoutResult("BATCH-1", "PENDING")

    def get_payout(self, batch_id):
        items = tuple((f"PI-{i.item_key}", self.payout_status, i.item_key)
                      for batch in self.payouts for i in batch)
        return PayoutResult(batch_id, "SUCCESS", items)
