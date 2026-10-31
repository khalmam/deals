from dataclasses import replace

import pytest

from deals.domain.chain import GENESIS, make_entry, terms_hash, verify


def build(n=4):
    entries, prev = [], None
    for i in range(n):
        ts = f"2026-11-0{i + 1}T00:00:00Z"
        prev = make_entry(prev, "deal-1", "OFFER_MADE", {"round": str(i)}, ts)
        entries.append(prev)
    return entries


def test_valid_chain_verifies():
    assert verify(build()) is None
    assert build()[0].prev_hash == GENESIS


def test_edited_payload_is_caught_at_that_entry():
    e = build()
    e[2] = replace(e[2], payload={"round": "999"})
    assert verify(e) == 2


def test_removed_entry_is_caught():
    e = build()
    del e[1]
    assert verify(e) == 1


def test_reordered_entries_are_caught():
    e = build()
    e[1], e[2] = e[2], e[1]
    assert verify(e) is not None


def test_unknown_kind_rejected():
    with pytest.raises(ValueError):
        make_entry(None, "d", "NOT_A_KIND", {}, "t")


def test_floats_rejected_in_payload():
    with pytest.raises(ValueError):
        make_entry(None, "d", "OFFER_MADE", {"price": 10.5}, "t")


def test_terms_hash_is_order_independent_and_stable():
    a = terms_hash({"price": "1800.00", "bundle": "standard"})
    b = terms_hash({"bundle": "standard", "price": "1800.00"})
    assert a == b and len(a) == 64
