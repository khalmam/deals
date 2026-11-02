from decimal import Decimal

import pytest

from deals.domain.money import Money
from engine.catalog import Bundle, CatalogError, LineItem
from engine.demo_card import demo_card, usd
from engine.pricing import payout_plan


def test_demo_card_list_prices():
    card = demo_card()
    assert [str(card.get(i).list_price) for i in ("basic", "standard", "premium")] == [
        "600.00 USD", "1800.00 USD", "3500.00 USD"]


def test_floor_above_list_is_rejected():
    with pytest.raises(CatalogError):
        Bundle("x", "X", (LineItem("a", usd(100)),), usd(101))


def test_mixed_currencies_are_rejected():
    with pytest.raises(CatalogError):
        Bundle("x", "X", (LineItem("a", Money.of(100, "EUR")),), usd(50))


def test_bad_line_items_are_rejected():
    for kwargs in ({"qty": 0}, {"sub_pct": 101, "sub_id": "s"}, {"sub_pct": 10}):
        with pytest.raises(CatalogError):
            LineItem("a", usd(10), **kwargs)


def test_unknown_bundle_raises():
    with pytest.raises(CatalogError):
        demo_card().get("gold")


def test_payouts_at_list_price():
    plan = payout_plan(demo_card().get("premium"), usd(3500))
    assert dict(plan.subs) == {"illustrator": usd(400), "webdev": usd(360)}
    assert plan.freelancer_net == usd(2740)


def test_discount_is_shared_and_everything_adds_up():
    bundle = demo_card().get("standard")
    for price in ("1500.00", "1633.33", "1799.99", "1800.00"):
        plan = payout_plan(bundle, usd(price))
        paid = sum((m.amount for _, m in plan.subs), Decimal(0))
        assert paid + plan.freelancer_net.amount == Decimal(price)
        assert plan.freelancer_net.amount > 0
    assert dict(payout_plan(bundle, usd("1500")).subs)["illustrator"] < usd(250)
