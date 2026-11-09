"""What the machines change for people and agents: the deal page's stage, the negotiation
fields agents read, payout visibility, and the hold-approval trace."""
import pytest

from deals.models import PaymentRecord
from deals.services.apply_webhook import record_item_status
from deals.services.deal_view import build_deal_view
from deals.services.live_deal import Deps, LiveError, approve_return
from deals.services.negotiation_protocol import open_negotiation
from deals.services.negotiation_views import list_negotiations, party_view
from deals.services.open_deal import agree_terms, open_deal
from deals.services.open_hold import open_hold
from deals.services.site_view import activity_feed
from tests.fakes import FakePayments
from tests.neg_helpers import terms

REPLIES = ["COUNTER", "ACCEPT", "REJECT"]


def test_an_open_agent_negotiation_is_not_shown_as_the_clients_move(parties):
    """Used to read 'negotiating': a reply form the API then refused with 409."""
    view = open_negotiation(parties["buyer"], parties["outside"].slug, terms("1300"),
                            "open-key-001")
    deal = build_deal_view(view["negotiation_id"])
    assert (deal["stage"], deal["waiting_on"], deal["next"]) == ("agent_negotiating", "agents", [])
    assert deal["standing"]["price"] == "1300.00" and deal["standing"]["by"] == "amanah-procurement"


def test_agents_are_told_whose_turn_it_is_and_what_they_may_send(wire, parties):
    buyer, prov = (wire.client_for(parties["buyer_token"]),
                   wire.client_for(parties["outside_token"]))
    opened = buyer.open(parties["outside"].slug, terms("1300"), "open-key-002")
    nid = opened["negotiation_id"]
    assert (opened["turn"], opened["lapsed"]) == ("provider", False)
    b, p = buyer.get(nid), prov.get(nid)
    assert (b["you"], b["your_move"], b["can_send"]) == ("buyer", False, ["WITHDRAW"])
    assert (p["you"], p["your_move"], p["can_send"]) == ("provider", True, REPLIES)
    mine = prov.inbox()[0]
    assert mine["your_move"] and mine["can_send"] == REPLIES and mine["turn"] == "provider"


def test_a_refusal_says_what_would_have_been_allowed(wire, parties):
    buyer = wire.client_for(parties["buyer_token"])
    opened = buyer.open(parties["outside"].slug, terms("1300"), "open-key-003")
    body = {"type": "COUNTER", "terms": terms("1350"), "in_reply_to": opened["head"]["proposal_id"]}
    status, err = wire("POST", f"/api/negotiations/{opened['negotiation_id']}/messages", body,
                       parties["buyer_token"], {"Idempotency-Key": "counter-key-1"})
    assert (status, err["code"], err["allowed"]) == (409, "NOT_YOUR_TURN", ["WITHDRAW"])


def test_a_closed_negotiation_has_no_turn_and_nothing_to_send(wire, parties):
    buyer, prov = (wire.client_for(parties["buyer_token"]),
                   wire.client_for(parties["outside_token"]))
    opened = buyer.open(parties["outside"].slug, terms("1300"), "open-key-004")
    nid, head = opened["negotiation_id"], opened["head"]
    prov.answer(nid, {"type": "REJECT", "in_reply_to": head["proposal_id"]}, "reject-key-01")
    done = buyer.get(nid)
    assert (done["status"], done["turn"], done["can_send"], done["your_move"]) == (
        "REJECTED", None, [], False)
    assert build_deal_view(nid)["stage"] == "walked_away"


def test_a_lapsed_proposal_is_visible_before_anything_closes_it(parties):
    old = "2020-01-01T00:00:00.000000Z"  # the default expiry is a day later: long gone
    view = open_negotiation(parties["buyer"], parties["outside"].slug, terms("1300"),
                            "open-key-005", now=old)
    seen = party_view(parties["outside"], view["negotiation_id"])
    assert (seen["status"], seen["lapsed"], seen["can_send"], seen["your_move"]) == (
        "OPEN", True, [], False)
    assert list_negotiations(parties["outside"])[0]["lapsed"] is True


def _captured_deal(state="CAPTURED"):
    deal = open_deal("t", "a@b.co")
    agree_terms(deal, {"total": "100", "currency": "USD"})
    deal.state = state
    deal.save()
    return deal


def test_a_closed_deal_is_not_shown_as_waiting_for_paypal(db):
    deal = _captured_deal("CLOSED")
    assert build_deal_view(deal.pk)["stage"] == "closed"


def test_a_failed_payout_is_surfaced_instead_of_waiting_forever(db):
    deal = _captured_deal()
    rec = PaymentRecord.objects.create(deal=deal, kind="PAYOUT_ITEM", paypal_id="X-1", amount=10,
                                       currency="USD", status="PENDING")
    assert build_deal_view(deal.pk)["stage"] == "captured"
    record_item_status(rec, "RETURNED", "wh-1", "pi-1")
    deal.refresh_from_db()
    view = build_deal_view(deal.pk)
    assert deal.state == "CAPTURED"  # recording is unchanged: nothing is silently rewritten
    assert (view["stage"], view["waiting_on"]) == ("payout_issue", "owner")
    assert view["payouts"] == {"total": 1, "waiting": 0, "done": 0, "failed": 1,
                               "needs_attention": True}
    assert [a["name"] for a in view["next"]] == ["refresh"]


def test_next_actions_are_followable_urls(db):
    deal = _captured_deal("HOLD_ACTIVE")
    nxt = {a["name"]: a for a in build_deal_view(deal.pk)["next"]}
    assert nxt["confirm_delivery"] == {"name": "confirm_delivery", "method": "POST",
                                       "href": f"/api/deals/{deal.pk}/delivery"}


def _hold_pending(pay):
    deal = open_deal("t", "a@b.co")
    agree_terms(deal, {"total": "100", "currency": "USD"})
    open_hold(deal, pay, "https://x/ok", "https://x/no")
    return deal


def test_a_hold_that_fails_the_terms_check_leaves_a_trace(db):
    pay = FakePayments(tamper_custom_id=True)
    deal = _hold_pending(pay)
    with pytest.raises(LiveError):
        approve_return(Deps(None, None, None, None, None, pay, None), str(deal.pk))
    last = deal.ledger.order_by("-seq").first()
    assert (last.kind, last.payload["tool"], last.payload["ok"]) == ("AGENT_ACTION",
                                                                    "confirm_hold", False)


def test_reloading_the_return_page_does_not_spam_the_ledger(db):
    pay = FakePayments()
    deal = _hold_pending(pay)
    deps = Deps(None, None, None, None, None, pay, None)
    approve_return(deps, str(deal.pk))
    before = deal.ledger.count()
    with pytest.raises(LiveError):  # already approved: refused, but not a failed approval
        approve_return(deps, str(deal.pk))
    assert deal.ledger.count() == before


def test_the_activity_feed_says_what_became_of_each_event(db):
    from deals.models import WebhookEvent
    item, other = "PAYMENT.PAYOUTS-ITEM.SUCCEEDED", "PAYMENT.CAPTURE.COMPLETED"
    for i, (kind, applied) in enumerate([(item, True), (item, False), (other, False)]):
        WebhookEvent.objects.create(event_id=f"WH-{i}", event_type=kind, applied=applied)
    assert sorted(e["status"] for e in activity_feed()) == ["applied", "ignored", "unapplied"]
