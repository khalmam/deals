"""What the owner lets the agent do on its own. Pure: no Django, no PayPal."""
import re
from dataclasses import dataclass, field
from decimal import Decimal

from .money import Money


class MandateViolation(Exception):
    """The agent tried something the owner did not allow."""


EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@dataclass(frozen=True)
class Mandate:
    allow_payouts: bool = False
    approved_subs: dict = field(default_factory=dict)  # sub_id -> PayPal email
    max_payout_pct: Decimal = Decimal("60")  # cap on sub-contractor share of the total

    def __post_init__(self):
        for sub_id, email in self.approved_subs.items():
            if not EMAIL.match(str(email)):
                raise MandateViolation(f"{sub_id}: {email!r} is not an email address")

    def to_dict(self):
        return {"allow_payouts": self.allow_payouts, "approved_subs": dict(self.approved_subs),
                "max_payout_pct": str(self.max_payout_pct)}

    @classmethod
    def from_dict(cls, d):
        d = d or {}
        return cls(bool(d.get("allow_payouts", False)), dict(d.get("approved_subs", {})),
                   Decimal(str(d.get("max_payout_pct", "60"))))


def check_payouts(mandate, payouts, total):
    """payouts: ((sub_id, Money), ...). Refuse unless every line is allowed.
    Returns ((sub_id, email, Money), ...)."""
    if not mandate.allow_payouts:
        raise MandateViolation("the mandate does not allow payouts")
    lines, paid = [], Money.of(0, total.currency)
    for sub_id, amount in payouts:
        email = mandate.approved_subs.get(sub_id)
        if not email:
            raise MandateViolation(f"{sub_id} is not an approved sub-contractor")
        lines.append((sub_id, email, amount))
        paid = paid + amount
    if paid.amount > total.amount * mandate.max_payout_pct / Decimal(100):
        raise MandateViolation("payouts exceed the share of the total the mandate allows")
    return tuple(lines)
