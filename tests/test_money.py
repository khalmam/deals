from decimal import Decimal

import pytest

from deals.domain.money import Money, MoneyError


def test_rejects_float():
    with pytest.raises(MoneyError):
        Money(10.5)


def test_rounds_to_cents_and_formats_for_paypal():
    m = Money.of("10.005")
    assert m.amount == Decimal("10.01")
    assert m.to_paypal() == {"currency_code": "USD", "value": "10.01"}
    assert m.to_payout() == {"currency": "USD", "value": "10.01"}


def test_currency_mismatch_raises():
    with pytest.raises(MoneyError):
        Money.of(1, "USD") + Money.of(1, "EUR")


def test_allocate_sums_exactly():
    parts = Money.of("100.00").allocate([1, 1, 1])
    assert sum((p.amount for p in parts), Decimal(0)) == Decimal("100.00")
    assert [str(p.amount) for p in parts] == ["33.34", "33.33", "33.33"]


def test_allocate_for_subcontractor_split():
    total = Money.of("1800.00")
    mine, sub = total.allocate([78, 22])
    assert mine + sub == total
    assert sub.amount == Decimal("396.00")


def test_ordering():
    assert Money.of(1) < Money.of(2)
    assert Money.of(2) <= Money.of(2)
