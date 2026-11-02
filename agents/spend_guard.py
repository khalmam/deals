"""Caps model calls. The store is injected, so a database-backed one survives restarts."""


class BudgetExceeded(RuntimeError):
    pass


class MemoryStore:
    def __init__(self):
        self._counts = {}

    def count(self, scope):
        return self._counts.get(scope, 0)

    def incr(self, scope):
        self._counts[scope] = self.count(scope) + 1


class SpendGuard:
    def __init__(self, store, per_deal=12, total=500):
        self.store, self.per_deal, self.total = store, per_deal, total

    def check_and_count(self, deal_ref):
        if self.store.count(deal_ref) >= self.per_deal or self.store.count("*") >= self.total:
            raise BudgetExceeded("model call budget used up")
        self.store.incr(deal_ref)
        self.store.incr("*")
