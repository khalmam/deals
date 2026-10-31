from .ledger import verify_ledger


def anchor_ok(deal, payments):
    """Does PayPal's own record of the hold carry our terms hash? None if there is no hold."""
    if not deal.auth_id:
        return None
    return payments.get_authorization(deal.auth_id).custom_id == deal.terms_hash


def build_receipt(deal, anchor=None):
    """Collect everything the receipt shows, as plain data the render layer can print."""
    entries = list(deal.ledger.order_by("seq"))
    bad = verify_ledger(deal)
    capture = deal.payments.filter(kind="CAPTURE").first()
    total = f"{deal.total_amount} {deal.currency}" if deal.total_amount is not None else ""
    return {
        "deal_id": str(deal.pk), "title": deal.title, "state": deal.state, "total": total,
        "terms_hash": deal.terms_hash,
        "head_hash": entries[-1].hash if entries else "",
        "paypal": {"order_id": deal.order_id, "authorization_id": deal.auth_id,
                   "capture_id": capture.paypal_id if capture else ""},
        "entries": [{"seq": e.seq, "kind": e.kind, "ts": e.ts, "hash": e.hash} for e in entries],
        "intact": bad is None, "broken_seq": None if bad is None else bad + 1,
        "anchor": anchor,
    }
