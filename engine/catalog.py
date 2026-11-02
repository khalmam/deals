"""Rate card: bundles made of line items, each bundle with a floor price. Pure."""
from dataclasses import dataclass, field
from decimal import Decimal

from deals.domain.money import Money


class CatalogError(ValueError):
    pass


@dataclass(frozen=True)
class LineItem:
    name: str
    rate: Money
    qty: int = 1
    sub_id: str | None = None  # approved sub-contractor who does this work
    sub_pct: int = 0  # percent of this line's price that goes to them

    def __post_init__(self):
        if self.qty < 1:
            raise CatalogError(f"{self.name}: quantity must be at least 1")
        if not 0 <= self.sub_pct <= 100:
            raise CatalogError(f"{self.name}: sub_pct must be between 0 and 100")
        if self.sub_pct and not self.sub_id:
            raise CatalogError(f"{self.name}: sub_pct needs a sub_id")

    @property
    def total(self):
        return self.rate.times(self.qty)


@dataclass(frozen=True)
class Bundle:
    id: str
    name: str
    items: tuple
    floor: Money

    def __post_init__(self):
        if not self.items:
            raise CatalogError(f"{self.id}: a bundle needs at least one line item")
        if {i.rate.currency for i in self.items} | {self.floor.currency} != {self.currency}:
            raise CatalogError(f"{self.id}: mixed currencies")
        if self.list_price < self.floor:
            raise CatalogError(f"{self.id}: floor is above the list price")

    @property
    def currency(self):
        return self.floor.currency

    @property
    def list_price(self):
        total = self.items[0].total
        for item in self.items[1:]:
            total = total + item.total
        return total


@dataclass(frozen=True)
class Policy:
    max_net_days: int = 30
    max_late_fee_pct: Decimal = Decimal("10")


@dataclass(frozen=True)
class RateCard:
    bundles: tuple
    policy: Policy = field(default_factory=Policy)

    def get(self, bundle_id):
        for b in self.bundles:
            if b.id == bundle_id:
                return b
        raise CatalogError(f"unknown bundle: {bundle_id}")
