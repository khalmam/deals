import json

import pytest
from django.db import DatabaseError, connection, transaction

from deals.models import Deal, LedgerEntry, Negotiation, NegotiationMessage
from deals.services import negotiation_protocol
from deals.services.negotiation_protocol import open_negotiation, submit_message
from deals.services.negotiation_rules import NegotiationError
from deals.services.negotiation_verify import verify_negotiation
from tests.helpers import as_admin
from tests.neg_helpers import MANDATE, agent, bundle, terms


@pytest.fixture
def opened(db, parties):
    view = open_negotiation(parties["buyer"], "freelance-ext", terms(), "open-key-0001")
    return view, parties


def reply(view, price="1500"):
    return {"type": "COUNTER", "in_reply_to": view["head"]["proposal_id"], "terms": terms(price)}


def break_ledger(monkeypatch):
    real = negotiation_protocol.append

    def append(deal, kind, payload, ts=None):
        if kind == "PROPOSAL_MADE":
            raise RuntimeError("the ledger write failed")
        return real(deal, kind, payload, ts)
    monkeypatch.setattr(negotiation_protocol, "append", append)


def test_a_failed_ledger_write_leaves_no_trace_when_opening(db, parties, monkeypatch):
    break_ledger(monkeypatch)
    with pytest.raises(RuntimeError):
        open_negotiation(parties["buyer"], "freelance-ext", terms(), "open-key-0002")
    assert (Deal.objects.count(), Negotiation.objects.count(),
            NegotiationMessage.objects.count(), LedgerEntry.objects.count()) == (0, 0, 0, 0)


def test_a_failed_ledger_write_leaves_the_history_unchanged(opened, monkeypatch):
    view, parties = opened
    break_ledger(monkeypatch)
    with pytest.raises(RuntimeError):
        submit_message(parties["outside"], view["negotiation_id"], reply(view), "counter-key-01")
    neg = Negotiation.objects.get()
    assert NegotiationMessage.objects.count() == 1 and neg.head_version == 1
    assert str(neg.head_proposal_id) == view["head"]["proposal_id"] and neg.status == "OPEN"


def test_a_failed_acceptance_does_not_half_agree_the_deal(opened, monkeypatch):
    view, parties = opened
    new = submit_message(parties["outside"], view["negotiation_id"], reply(view, "1350"),
                         "counter-key-02")
    monkeypatch.setattr(negotiation_protocol, "agree_proposal",
                        lambda *a: (_ for _ in ()).throw(RuntimeError("boom")))
    accept = {"type": "ACCEPT", "in_reply_to": new["head"]["proposal_id"],
              "terms_hash": new["head"]["terms_hash"]}
    with pytest.raises(RuntimeError):
        submit_message(parties["buyer"], view["negotiation_id"], accept, "accept-key-001")
    assert NegotiationMessage.objects.count() == 2
    assert Negotiation.objects.get().status == "OPEN" and Deal.objects.get().state != "AGREED"


def test_history_verifies_and_every_message_is_in_the_ledger(opened):
    view, parties = opened
    submit_message(parties["outside"], view["negotiation_id"], reply(view), "counter-key-03")
    result = verify_negotiation(view["negotiation_id"])
    assert result == {"intact": True, "problems": []}
    hashes = [e.payload["message_hash"] for e in LedgerEntry.objects.filter(
        kind="PROPOSAL_MADE").order_by("seq")]
    assert hashes == [m.message_hash for m in NegotiationMessage.objects.order_by("version")]


def test_tampering_with_a_message_is_detected(opened):
    view, _ = opened
    as_admin("deals_negotiationmessage")
    NegotiationMessage.objects.update(terms=terms("1"))
    problems = verify_negotiation(view["negotiation_id"])["problems"]
    assert any("terms do not match" in p for p in problems)


def test_tampering_with_the_ledger_copy_is_detected(opened):
    view, _ = opened
    as_admin("deals_ledgerentry")
    entry = LedgerEntry.objects.get(kind="PROPOSAL_MADE")
    LedgerEntry.objects.filter(pk=entry.pk).update(payload={**entry.payload, "price": "1"})
    assert not verify_negotiation(view["negotiation_id"])["intact"]


def test_a_missing_ledger_entry_is_detected(opened):
    view, _ = opened
    as_admin("deals_ledgerentry")
    LedgerEntry.objects.filter(kind="PROPOSAL_MADE").delete()
    problems = verify_negotiation(view["negotiation_id"])["problems"]
    assert any("ledger entries" in p for p in problems)


def test_messages_cannot_be_edited_or_deleted_through_the_model(opened):
    msg = NegotiationMessage.objects.get()
    msg.terms = {}
    with pytest.raises(RuntimeError):
        msg.save()
    with pytest.raises(RuntimeError):
        msg.delete()


def test_provider_guard_protects_only_the_providers_own_sends(opened, db):
    hosted, _ = agent("Floor Holder", "PROVIDER", services=[bundle("1037")],
                      mandate=MANDATE, hosted=True)
    _, parties = opened
    low = open_negotiation(parties["buyer"], "floor-holder", terms("900"), "open-key-0003")
    assert low["status"] == "OPEN"  # the buyer is told nothing about the floor
    accept = {"type": "ACCEPT", "in_reply_to": low["head"]["proposal_id"],
              "terms_hash": low["head"]["terms_hash"]}
    with pytest.raises(NegotiationError) as refused:
        submit_message(hosted, low["negotiation_id"], accept, "accept-key-002")
    assert refused.value.code == "BELOW_YOUR_FLOOR" and refused.value.status == 422
    assert "1037" not in json.dumps([str(refused.value), refused.value.extra])
    cheap = reply(low, "900")
    with pytest.raises(NegotiationError):
        submit_message(hosted, low["negotiation_id"], cheap, "counter-key-04")


@pytest.mark.skipif(connection.vendor != "postgresql", reason="the trigger exists on Postgres")
def test_postgres_itself_refuses_to_edit_or_delete_a_message(opened):
    for change in (lambda: NegotiationMessage.objects.update(terms={}),
                   lambda: NegotiationMessage.objects.all().delete()):
        with pytest.raises(DatabaseError, match="append-only"), transaction.atomic():
            change()
    assert NegotiationMessage.objects.count() == 1
