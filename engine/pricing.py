"""Who gets what from an agreed price. Pure; the split always adds up to the price."""
from dataclasses import dataclass
from decimal import Decimal

from deals.domain.money import Money


@dataclass(frozen=True)
class PayoutPlan:
    subs: tuple  # ((sub_id, Money), ...) sorted by sub_id
    freelancer_net: Money


def payout_plan(bundle, final_price):
    """Spread the agreed price over the line items in proportion to their list prices, then
    pay each sub-contractor their percentage of their lines. A discount is shared fairly."""
    weights = [int(item.total.amount * 100) for item in bundle.items]
    line_prices = final_price.allocate(weights)
    zero = Money.of(0, final_price.currency)
    owed = {}
    for item, line in zip(bundle.items, line_prices, strict=True):
        if item.sub_id and item.sub_pct:
            share = line.times(Decimal(item.sub_pct) / Decimal(100))
            owed[item.sub_id] = owed.get(item.sub_id, zero) + share
    paid = zero
    for amount in owed.values():
        paid = paid + amount
    return PayoutPlan(tuple(sorted(owed.items())), final_price - paid)
