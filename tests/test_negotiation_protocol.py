import pytest

from deals.models import Deal, LedgerEntry, Negotiation, NegotiationMessage
from deals.services.negotiation_protocol import open_negotiation, submit_message
from deals.services.negotiation_rules import NegotiationError
from tests.neg_helpers import agent, terms

T0 = "2026-01-01T00:00:00.000000Z"
T1 = "2026-01-03T00:00:00.000000Z"


@pytest.fixture
def started(wire, parties):
    """An open negotiation with the external provider: buyer PROPOSE at 1300."""
    buyer = wire.client_for(parties["buyer_token"])
    provider = wire.client_for(parties["outside_token"])
    view = buyer.open("freelance-ext", terms(), "buyer-open-0001")
    return buyer, provider, view


def counter(provider, view, price="1500", key="prov-counter-1"):
    body = {"type": "COUNTER", "in_reply_to": view["head"]["proposal_id"],
            "terms": terms(price)}
    return provider.answer(view["negotiation_id"], body, key)


def refused(call, *args):
    with pytest.raises(Exception) as caught:
        call(*args)
    return caught.value


def test_open_records_message_and_ledger_together(started):
    _, _, view = started
    msg, entry = NegotiationMessage.objects.get(), LedgerEntry.objects.get(kind="PROPOSAL_MADE")
    assert view["status"] == "OPEN" and view["head"]["type"] == "PROPOSE"
    assert entry.payload["message_hash"] == msg.message_hash
    assert entry.payload["proposal_id"] == str(msg.proposal_id) == view["head"]["proposal_id"]


def test_retry_with_same_key_creates_nothing_new(started):
    buyer, _, first = started
    again = buyer.open("freelance-ext", terms(), "buyer-open-0001")
    assert again["replayed"] is True and again["negotiation_id"] == first["negotiation_id"]
    assert (Deal.objects.count(), Negotiation.objects.count(),
            NegotiationMessage.objects.count()) == (1, 1, 1)


def test_same_key_different_request_is_a_conflict(started):
    buyer, _, _ = started
    assert refused(buyer.open, "freelance-ext", terms("1250"), "buyer-open-0001").code == \
        "IDEMPOTENCY_CONFLICT"


def test_a_key_is_required(wire, parties):
    buyer = wire.client_for(parties["buyer_token"])
    assert refused(buyer.open, "freelance-ext", terms(), "").code == "IDEMPOTENCY_KEY_REQUIRED"


def test_message_type_and_negotiation_status_are_separate(started):
    _, provider, view = started
    after = counter(provider, view)
    assert after["head"]["type"] == "COUNTER" and after["status"] == "OPEN"
    assert [m["version"] for m in after["messages"]] == [1, 2]


def test_a_stale_reply_is_refused_with_the_current_head(started):
    buyer, provider, view = started
    new = counter(provider, view)
    old = refused(provider.answer, view["negotiation_id"],
                  {"type": "WITHDRAW", "in_reply_to": view["head"]["proposal_id"]}, "stale-0001x")
    assert old.code == "STALE"
    reply = {"type": "COUNTER", "in_reply_to": view["head"]["proposal_id"], "terms": terms()}
    assert refused(buyer.answer, view["negotiation_id"], reply, "buyer-stale-1").code == "STALE"
    assert new["head"]["version"] == 2


def test_turn_order(started):
    buyer, provider, view = started
    nid, head = view["negotiation_id"], view["head"]["proposal_id"]
    own = {"type": "COUNTER", "in_reply_to": head, "terms": terms("1200")}
    assert refused(buyer.answer, nid, own, "buyer-own-0001").code == "NOT_YOUR_TURN"
    assert refused(provider.answer, nid, {"type": "WITHDRAW", "in_reply_to": head},
                   "prov-wd-0001").code == "NOT_YOUR_PROPOSAL"


def test_accept_must_quote_the_exact_head_and_carry_no_terms(started):
    buyer, provider, view = started
    new = counter(provider, view, "1350")
    nid, head = view["negotiation_id"], new["head"]
    wrong = {"type": "ACCEPT", "in_reply_to": head["proposal_id"], "terms_hash": "0" * 64}
    assert refused(buyer.answer, nid, wrong, "buyer-acc-0001").code == "TERMS_MISMATCH"
    sneaky = {"type": "ACCEPT", "in_reply_to": head["proposal_id"],
              "terms_hash": head["terms_hash"], "terms": terms("1")}
    assert refused(buyer.answer, nid, sneaky, "buyer-acc-0002").code == "TERMS_NOT_ALLOWED"
    ok = {"type": "ACCEPT", "in_reply_to": head["proposal_id"], "terms_hash": head["terms_hash"]}
    done = buyer.answer(nid, ok, "buyer-acc-0003")
    assert done["status"] == "AGREED" and done["deal_state"] == "AGREED"
    agreed = Deal.objects.get().terms
    assert agreed["total"] == "1350.00" and agreed["net_days"] == "14"
    assert agreed["proposal_id"] == head["proposal_id"]
    assert agreed["delivery_days"] == "21" and agreed["late_fee_pct"] == "2"


@pytest.mark.parametrize("kind,status", [("REJECT", "REJECTED"), ("WITHDRAW", "WITHDRAWN")])
def test_closing_moves(started, kind, status):
    buyer, provider, view = started
    new = counter(provider, view)
    side, who = (buyer, "buyer") if kind == "REJECT" else (provider, "provider")
    done = side.answer(view["negotiation_id"],
                       {"type": kind, "in_reply_to": new["head"]["proposal_id"]}, f"{who}-end-001")
    assert done["status"] == status and Deal.objects.get().state == "WALKED_AWAY"
    assert LedgerEntry.objects.filter(kind="NEGOTIATION_CLOSED").count() == 1
    again = refused(side.answer, view["negotiation_id"],
                    {"type": kind, "in_reply_to": new["head"]["proposal_id"]}, f"{who}-end-002")
    assert again.code == "CLOSED"


def test_a_standing_proposal_expires_and_stays_expired(db, parties):
    first = open_negotiation(parties["buyer"], "freelance-ext", terms(), "open-expiry-1",
                             {"expires_in": 60}, now=T0)
    body = {"type": "COUNTER", "in_reply_to": first["head"]["proposal_id"],
            "terms": terms("1500")}
    with pytest.raises(NegotiationError) as late:
        submit_message(parties["outside"], first["negotiation_id"], body, "late-key-0001", now=T1)
    assert (late.value.code, late.value.status) == ("EXPIRED", 410)
    assert Negotiation.objects.get().status == "EXPIRED"
    assert Deal.objects.get().state == "WALKED_AWAY"
    with pytest.raises(NegotiationError) as closed:
        submit_message(parties["outside"], first["negotiation_id"], body, "late-key-0002", now=T1)
    assert closed.value.code == "CLOSED"


def test_scope_cannot_change_mid_negotiation(started):
    _, provider, view = started
    euros = terms("1500")
    euros["price"]["currency"] = "EUR"
    other = {"type": "COUNTER", "in_reply_to": view["head"]["proposal_id"], "terms": euros}
    assert refused(provider.answer, view["negotiation_id"], other, "scope-key-0001").code == \
        "SCOPE_CHANGE"


def test_only_parties_can_read_or_write(wire, parties, started):
    _, _, view = started
    _, token = agent("Stranger", "BUYER", mandate={"max_deal": "9999"})
    other = wire.client_for(token)
    assert refused(other.get, view["negotiation_id"]).status == 403
    assert refused(wire.client_for("dl_wrong").get, view["negotiation_id"]).status == 401
    assert wire.client_for(parties["buyer_token"]).get(view["negotiation_id"])["status"] == "OPEN"


def test_the_buyers_own_budget_binds_it(started, wire, parties):
    buyer, provider, view = started
    over = refused(buyer.open, "freelance-ext", terms("1500"), "buyer-over-001")
    assert over.code == "OVER_BUDGET"
    new = counter(provider, view, "1500")
    accept = {"type": "ACCEPT", "in_reply_to": new["head"]["proposal_id"],
              "terms_hash": new["head"]["terms_hash"]}
    assert refused(buyer.answer, view["negotiation_id"], accept, "buyer-acc-9999").code == \
        "OVER_BUDGET"


def test_legacy_free_text_flow_is_closed_to_protocol_deals(started, wire, parties):
    buyer, _, view = started
    status, body = wire("POST", f"/api/deals/{view['negotiation_id']}/offers",
                        {"message": "I can pay 1000"}, parties["buyer_token"])
    assert status == 409 and "api/negotiations" in body["error"]
