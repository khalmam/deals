from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from deals.domain.money import Money
from engine.catalog import Bundle, LineItem, RateCard
from engine.demo_card import demo_card, usd
from engine.negotiation import Offer, opening_ask, respond, validate_offer

CARD = demo_card()


def test_opening_ask_is_the_list_price():
    assert opening_ask(CARD, "standard").price == usd(1800)


def test_offer_inside_the_card_is_ok():
    assert validate_offer(CARD, Offer("standard", usd(1600), net_days=14, late_fee_pct=5)).ok


@pytest.mark.parametrize("offer,reason", [
    (Offer("standard", usd("1499.99")), "BELOW_FLOOR"),
    (Offer("standard", usd("1800.01")), "ABOVE_LIST"),
    (Offer("standard", usd(1600), net_days=31), "NET_DAYS_OUT_OF_RANGE"),
    (Offer("standard", usd(1600), late_fee_pct=11), "LATE_FEE_OUT_OF_RANGE"),
    (Offer("gold", usd(1600)), "UNKNOWN_BUNDLE"),
    (Offer("standard", Money.of(1600, "EUR")), "CURRENCY_MISMATCH"),
])
def test_offers_outside_the_card_are_rejected_with_a_code(offer, reason):
    v = validate_offer(CARD, offer)
    assert not v.ok and reason in v.reasons


def test_float_late_fee_is_refused():
    with pytest.raises(TypeError):
        Offer("standard", usd(1600), late_fee_pct=2.5)


def test_a_lowballing_client_walks_through_the_whole_schedule():
    counters = []
    for k in range(1, 6):
        d = respond(CARD, "standard", usd(1000), k)
        assert d.action == "ASK"
        counters.append(str(d.price.amount))
    assert counters == ["1740.00", "1680.00", "1620.00", "1560.00", "1500.00"]
    assert respond(CARD, "standard", usd(1000), 6).action == "WALK_AWAY"


def test_client_meeting_our_current_ask_is_accepted():
    assert respond(CARD, "standard", usd(1800), 1).action == "ACCEPT"
    d = respond(CARD, "standard", usd(1700), 2)  # our ask was 1740 -> not yet
    assert d.action == "ASK"
    assert respond(CARD, "standard", usd(1740), 2).action == "ACCEPT"


def test_client_reaching_the_floor_after_the_last_counter_is_accepted():
    d = respond(CARD, "standard", usd(1500), 6)
    assert d.action == "ACCEPT" and d.price == usd(1500)


def test_offer_above_list_is_accepted_only_at_list():
    d = respond(CARD, "standard", usd(2500), 1)
    assert d.action == "ACCEPT" and d.price == usd(1800)


def test_bad_inputs_raise():
    with pytest.raises(ValueError):
        respond(CARD, "standard", Money.of(100, "EUR"), 1)
    with pytest.raises(ValueError):
        respond(CARD, "standard", usd(100), 0)


@settings(max_examples=300, deadline=None)
@given(list_cents=st.integers(1_000, 2_000_000), floor_pct=st.integers(0, 100),
       prices=st.lists(st.integers(0, 4_000_000), min_size=1, max_size=14),
       rounds=st.integers(1, 8))
def test_no_decision_ever_leaves_the_band_and_asks_only_fall(list_cents, floor_pct, prices,
                                                             rounds):
    list_price = Money(Decimal(list_cents) / Decimal(100))
    floor = Money(Decimal(list_cents * floor_pct // 100) / Decimal(100))
    card = RateCard((Bundle("b", "B", (LineItem("x", list_price),), floor),))
    last_ask = list_price
    for k, cents in enumerate(prices, start=1):
        d = respond(card, "b", Money(Decimal(cents) / Decimal(100)), k, rounds)
        if d.price is not None:
            assert floor <= d.price <= list_price
        if d.action == "ASK":
            assert d.price <= last_ask
            last_ask = d.price
        if d.action != "ASK":
            break


@settings(max_examples=300, deadline=None)
@given(list_cents=st.integers(1_000, 2_000_000), floor_pct=st.integers(0, 100),
       cents=st.integers(0, 4_000_000), k=st.integers(1, 60), rounds=st.integers(1, 8))
def test_any_round_number_and_any_price_stays_in_the_band(list_cents, floor_pct, cents, k,
                                                          rounds):
    """The function must be safe even if a caller loses count of the rounds."""
    list_price = Money(Decimal(list_cents) / Decimal(100))
    floor = Money(Decimal(list_cents * floor_pct // 100) / Decimal(100))
    card = RateCard((Bundle("b", "B", (LineItem("x", list_price),), floor),))
    d = respond(card, "b", Money(Decimal(cents) / Decimal(100)), k, rounds)
    if d.action == "WALK_AWAY":
        assert d.price is None
    else:
        assert floor <= d.price <= list_price
