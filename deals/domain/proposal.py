"""Negotiation proposals: strict terms, one canonical form, and the hashes built on it.
Pure: standard library only. Identical terms always give identical bytes and hashes."""
import hashlib
import json
import re
import unicodedata
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

MESSAGE_TYPES = ("PROPOSE", "COUNTER", "ACCEPT", "REJECT", "WITHDRAW")
STATUSES = ("OPEN", "AGREED", "REJECTED", "WITHDRAWN", "EXPIRED")
WITH_TERMS = ("PROPOSE", "COUNTER")
CENT = Decimal("0.01")
TERMS_TAG = "deals.terms.v1\n"  # separates these hashes from every other hash we make
MESSAGE_TAG = "deals.message.v1\n"
ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")
LIMITS = {"delivery_days": (1, 365), "net_days": (0, 90), "grace_days": (0, 30)}


class ProposalError(ValueError):
    def __init__(self, message, code="INVALID_TERMS"):
        super().__init__(message)
        self.code = code


def _nfc(text):
    return unicodedata.normalize("NFC", text)


def _only(raw, allowed, required, where):
    if not isinstance(raw, dict):
        raise ProposalError(f"{where} must be an object")
    extra = sorted(set(raw) - set(allowed))
    if extra:
        raise ProposalError(f"{where}: unknown field {extra[0]}")
    for key in required:
        if key not in raw:
            raise ProposalError(f"{where}: {key} is required")
    for key, value in raw.items():
        if value is None:  # null is never a value; leave a field out to take its default
            raise ProposalError(f"{where}: {key} must not be null")
    return raw


def _int(value, name):
    low, high = LIMITS[name]
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ProposalError(f"{name} must be a whole number from {low} to {high}")
    return value


def _decimal(value, name):
    if isinstance(value, (bool, float)) or not isinstance(value, (str, int)):
        raise ProposalError(f"{name} must be a string or integer, never a float")
    try:
        number = Decimal(str(value).strip())
    except InvalidOperation as exc:
        raise ProposalError(f"{name} is not a number") from exc
    if not number.is_finite():
        raise ProposalError(f"{name} is not a number")
    return number


def _amount(raw):
    raw = _only(raw, ("amount", "currency"), ("amount", "currency"), "price")
    amount = _decimal(raw["amount"], "price.amount")
    if amount != amount.quantize(CENT, rounding=ROUND_HALF_UP):
        raise ProposalError("price.amount has more than two decimal places")
    if not Decimal(0) < amount <= Decimal(10) ** 9:
        raise ProposalError("price.amount is out of range")
    currency = _nfc(str(raw["currency"])).upper()
    if not re.fullmatch(r"[A-Z]{3}", currency):
        raise ProposalError("price.currency must be a three-letter code")
    return {"amount": str(amount.quantize(CENT)), "currency": currency}


def _fee(value):
    fee = _decimal(value, "late.fee_pct")
    if not Decimal(0) <= fee <= Decimal(100) or fee != fee.quantize(Decimal("0.0001")):
        raise ProposalError("late.fee_pct must be 0 to 100 with at most four decimals")
    return format(fee.normalize(), "f") if fee else "0"


def parse_terms(raw):
    """Validate untrusted terms and return the canonical form: every field present,
    defaults filled in, numbers normalised. Hash this, never the raw input."""
    raw = _only(raw, ("bundle_id", "price", "delivery_days", "payment", "late"),
                ("bundle_id", "price", "delivery_days"), "terms")
    bundle_id = _nfc(str(raw["bundle_id"]))
    if not ID.match(bundle_id):
        raise ProposalError("bundle_id is not valid")
    pay = _only(raw.get("payment", {}), ("net_days",), (), "payment")
    late = _only(raw.get("late", {}), ("fee_pct", "grace_days"), (), "late")
    return {"bundle_id": bundle_id, "price": _amount(raw["price"]),
            "delivery_days": _int(raw["delivery_days"], "delivery_days"),
            "payment": {"net_days": _int(pay.get("net_days", 0), "net_days")},
            "late": {"fee_pct": _fee(late.get("fee_pct", "0")),
                     "grace_days": _int(late.get("grace_days", 0), "grace_days")}}


def _clean(obj):
    if isinstance(obj, dict):
        return {_nfc(str(k)): _clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_clean(v) for v in obj]
    if isinstance(obj, str):
        return _nfc(obj)
    if obj is None or isinstance(obj, float):
        raise ProposalError("null and float values cannot be hashed", "NOT_CANONICAL")
    return obj


def canonical_bytes(obj):
    """Sorted keys, no whitespace, NFC text, UTF-8 bytes. Null and floats are refused."""
    return json.dumps(_clean(obj), sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def _digest(tag, obj):
    return hashlib.sha256(tag.encode() + canonical_bytes(obj)).hexdigest()


def terms_hash(canonical_terms):
    return _digest(TERMS_TAG, canonical_terms)


def message_hash(*, proposal_id, negotiation_id, version, msg_type, in_reply_to, sender,
                 terms_hash_, expires_at, created_at, prev_hash):
    """Binds a message to its place in the history. No field is ever null: an absent
    reply target or expiry is the empty string."""
    return _digest(MESSAGE_TAG, {
        "proposal_id": str(proposal_id), "negotiation_id": str(negotiation_id),
        "version": version, "type": msg_type, "in_reply_to": str(in_reply_to or ""),
        "sender": str(sender), "terms_hash": terms_hash_, "expires_at": expires_at or "",
        "created_at": created_at, "prev_hash": prev_hash})


def request_hash(body):
    """Fingerprint of a request body, for idempotency: the same retry gives the same value."""
    return hashlib.sha256(canonical_bytes(body)).hexdigest()
