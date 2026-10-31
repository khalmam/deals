"""Tamper-evident hash chain, one chain per deal. Adapted from the Paper Trail ledger
(my earlier project). Pure: standard library only."""
import hashlib
import json
from dataclasses import dataclass

from .vocab import KINDS

GENESIS = "0" * 64


def _reject_floats(obj):
    if isinstance(obj, float):
        raise ValueError("floats are not allowed in ledger payloads; use strings")
    if isinstance(obj, dict):
        for v in obj.values():
            _reject_floats(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _reject_floats(v)


def canonical(obj):
    _reject_floats(obj)
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_hex(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def terms_hash(terms):
    """The commitment that is also stored in PayPal's custom_id."""
    return sha256_hex(canonical(terms))


@dataclass(frozen=True)
class Entry:
    deal_id: str
    seq: int
    kind: str
    payload: dict
    ts: str
    prev_hash: str
    hash: str


def compute_hash(prev_hash, deal_id, seq, kind, payload, ts):
    body = {"prev": prev_hash, "deal": deal_id, "seq": seq, "kind": kind,
            "payload": payload, "ts": ts}
    return sha256_hex(canonical(body))


def make_entry(prev, deal_id, kind, payload, ts):
    if kind not in KINDS:
        raise ValueError(f"unknown ledger kind: {kind}")
    seq = 1 if prev is None else prev.seq + 1
    prev_hash = GENESIS if prev is None else prev.hash
    return Entry(deal_id, seq, kind, payload, ts, prev_hash,
                 compute_hash(prev_hash, deal_id, seq, kind, payload, ts))


def verify(entries):
    """Return None if the chain is intact, else the index of the first bad entry."""
    prev_hash, prev_seq = GENESIS, 0
    for i, e in enumerate(entries):
        ok = (e.seq == prev_seq + 1 and e.prev_hash == prev_hash and e.kind in KINDS
              and e.hash == compute_hash(e.prev_hash, e.deal_id, e.seq, e.kind, e.payload, e.ts))
        if not ok:
            return i
        prev_hash, prev_seq = e.hash, e.seq
    return None
