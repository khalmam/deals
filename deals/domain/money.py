"""Money as Decimal, never float. Pure: standard library only."""
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

CENT = Decimal("0.01")


class MoneyError(ValueError):
    pass


@dataclass(frozen=True)
class Money:
    amount: Decimal
    currency: str = "USD"

    def __post_init__(self):
        if isinstance(self.amount, float):
            raise MoneyError("floats are not allowed; use str, int or Decimal")
        try:
            amt = Decimal(self.amount).quantize(CENT, rounding=ROUND_HALF_UP)
        except (InvalidOperation, TypeError) as exc:
            raise MoneyError(f"invalid amount: {self.amount!r}") from exc
        cur = str(self.currency).upper()
        if len(cur) != 3 or not cur.isalpha():
            raise MoneyError(f"invalid currency: {self.currency!r}")
        object.__setattr__(self, "amount", amt)
        object.__setattr__(self, "currency", cur)

    @classmethod
    def of(cls, value, currency="USD"):
        return cls(value, currency)

    def _same(self, other):
        if self.currency != other.currency:
            raise MoneyError(f"currency mismatch: {self.currency} vs {other.currency}")

    def __add__(self, other):
        self._same(other)
        return Money(self.amount + other.amount, self.currency)

    def __sub__(self, other):
        self._same(other)
        return Money(self.amount - other.amount, self.currency)

    def __lt__(self, other):
        self._same(other)
        return self.amount < other.amount

    def __le__(self, other):
        self._same(other)
        return self.amount <= other.amount

    def times(self, factor):
        if isinstance(factor, float):
            raise MoneyError("floats are not allowed")
        return Money(self.amount * Decimal(factor), self.currency)

    def allocate(self, ratios):
        """Split into len(ratios) parts proportional to ratios; parts always sum exactly."""
        total = sum(ratios)
        if total <= 0 or any(r < 0 for r in ratios):
            raise MoneyError("ratios must be non-negative and sum to more than zero")
        cents = int((self.amount / CENT).to_integral_value())
        parts = [cents * r // total for r in ratios]
        for i in range(cents - sum(parts)):
            parts[i % len(parts)] += 1
        return [Money(Decimal(p) * CENT, self.currency) for p in parts]

    def to_paypal(self):
        """Orders/Payments/Invoicing shape."""
        return {"currency_code": self.currency, "value": f"{self.amount:.2f}"}

    def to_payout(self):
        """The Payouts API names the field 'currency', not 'currency_code'."""
        return {"currency": self.currency, "value": f"{self.amount:.2f}"}

    def __str__(self):
        return f"{self.amount:.2f} {self.currency}"
