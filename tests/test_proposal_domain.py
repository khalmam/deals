import pytest

from deals.domain.proposal import (
    ProposalError,
    canonical_bytes,
    message_hash,
    parse_terms,
    request_hash,
    terms_hash,
)

BASE = {"bundle_id": "standard", "price": {"amount": "1400", "currency": "usd"},
        "delivery_days": 21}


def test_equivalent_terms_have_one_hash():
    spelled_out = {"late": {"grace_days": 0, "fee_pct": "0.0"}, "delivery_days": 21,
                   "payment": {"net_days": 0}, "bundle_id": "standard",
                   "price": {"currency": "USD", "amount": 1400}}
    assert terms_hash(parse_terms(BASE)) == terms_hash(parse_terms(spelled_out))
    assert terms_hash(parse_terms(BASE)) == terms_hash(
        parse_terms({**BASE, "price": {"amount": "1400.00", "currency": "USD"}}))


def test_omitted_fields_take_explicit_defaults():
    parsed = parse_terms(BASE)
    assert parsed["payment"] == {"net_days": 0}
    assert parsed["late"] == {"fee_pct": "0", "grace_days": 0}
    assert parsed["price"] == {"amount": "1400.00", "currency": "USD"}


@pytest.mark.parametrize("fee", ["2", "2.0", "2.00", "02", 2])
def test_fee_is_normalised(fee):
    assert parse_terms({**BASE, "late": {"fee_pct": fee}})["late"]["fee_pct"] == "2"


def test_canonical_bytes_are_sorted_compact_and_nfc():
    raw = canonical_bytes({"b": 1, "a": {"y": "x", "x": "y"}})
    assert raw == b'{"a":{"x":"y","y":"x"},"b":1}'
    assert canonical_bytes({"k": "\u00e9"}) == canonical_bytes({"k": "e\u0301"})
    assert "é".encode() in canonical_bytes({"k": "é"})  # real UTF-8, not \u escapes


@pytest.mark.parametrize("bad", [
    {**BASE, "price": {"amount": 1400.0, "currency": "USD"}},  # float
    {**BASE, "price": {"amount": "1400.005", "currency": "USD"}},  # hidden rounding
    {**BASE, "price": {"amount": "0", "currency": "USD"}},
    {**BASE, "delivery_days": True},
    {**BASE, "delivery_days": 0},
    {**BASE, "payment": None},  # null is never a value
    {**BASE, "late": {"fee_pct": None}},
    {**BASE, "floor": "1000"},  # unknown field
    {**BASE, "bundle_id": "Standard Pack!"},
    {"bundle_id": "standard", "delivery_days": 21},  # price missing
])
def test_bad_terms_are_refused(bad):
    with pytest.raises(ProposalError):
        parse_terms(bad)


def test_null_and_float_cannot_be_hashed():
    for bad in ({"a": None}, {"a": 1.5}):
        with pytest.raises(ProposalError):
            canonical_bytes(bad)


def test_every_message_field_changes_the_hash():
    args = dict(proposal_id="p", negotiation_id="n", version=1, msg_type="PROPOSE",
                in_reply_to=None, sender="s", terms_hash_="t", expires_at="e",
                created_at="c", prev_hash="0" * 64)
    base = message_hash(**args)
    for field, other in [("version", 2), ("msg_type", "COUNTER"), ("sender", "x"),
                         ("terms_hash_", "u"), ("prev_hash", "1" * 64), ("in_reply_to", "q")]:
        assert message_hash(**{**args, field: other}) != base
    assert message_hash(**{**args, "in_reply_to": ""}) == base  # absent is the empty string


def test_request_hash_ignores_key_order():
    assert request_hash({"a": 1, "b": {"c": 2, "d": 3}}) == request_hash(
        {"b": {"d": 3, "c": 2}, "a": 1})
