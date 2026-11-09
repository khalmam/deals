"""The machines as data: structure, agreement between tables and the code that applies them,
and the generated docs. Pure tests need no database."""
import itertools
import re
import uuid
from pathlib import Path

import pytest
from django.template.loader import render_to_string

from deals.domain.machine import IllegalTransition
from deals.domain.machines import ALL, reference
from deals.domain.negotiation_machine import (
    NEGOTIATION,
    SENDER,
    Move,
    Status,
    legal_moves,
    turn,
)
from deals.domain.payout import Bucket, classify, normalise, stored_status, summarise
from deals.domain.stage import REFINEMENTS, STAGE_OF_STATE, STAGES, stage_for
from deals.domain.states import DEAL, Event, State
from deals.management.commands.machines import splice
from deals.services.negotiation_protocol import CLOSING
from deals.services.negotiation_rules import Head, NegotiationError, check_turn

DOC = Path(__file__).resolve().parent.parent / "docs" / "STATE_MACHINES.md"


def test_every_machine_is_structurally_sound():
    assert [p for m in ALL for p in m.problems()] == []


def test_terminal_states():
    assert DEAL.terminal() == {State.CLOSED, State.VOIDED, State.WALKED_AWAY}
    assert NEGOTIATION.terminal() == set(Status) - {Status.OPEN}  # a COUNTER loop is not an exit


def test_the_primitive_refuses_and_explains():
    assert DEAL.can(State.HOLD_ACTIVE, Event.VOID) and not DEAL.can(State.HOLD_ACTIVE,
                                                                    Event.CAPTURE_DONE)
    with pytest.raises(IllegalTransition, match="not allowed in state"):
        DEAL.step(State.DRAFT, Event.CLOSE)
    assert NEGOTIATION.step("OPEN", "COUNTER") is Status.OPEN  # plain strings are accepted


def test_closing_moves_come_from_the_table():
    assert CLOSING == {Move.ACCEPT: "AGREED", Move.REJECT: "REJECTED",
                       Move.WITHDRAW: "WITHDRAWN"}
    assert NEGOTIATION.step(Status.OPEN, Move.EXPIRE) is Status.EXPIRED


def test_check_turn_agrees_with_legal_moves_for_every_combination():
    """The turn table and the code that enforces it cannot drift apart."""
    for status, head_role, role, msg in itertools.product(
            Status, ("buyer", "provider"), ("buyer", "provider"), SENDER):
        head = Head("p1", 3, head_role, "h" * 64)
        has_terms = msg == "COUNTER"
        try:
            check_turn(status.value, head, role, msg, "p1", "h" * 64, has_terms)
            refused = None
        except NegotiationError as exc:
            refused = exc.code
        legal = msg in legal_moves(status.value, head_role, role)
        assert (refused is None) == legal, (status, head_role, role, msg, refused)
        if refused:
            assert refused in {"CLOSED", "NOT_YOUR_TURN", "NOT_YOUR_PROPOSAL"}


def test_a_lapsed_proposal_allows_nothing_and_a_closed_one_has_no_turn():
    assert legal_moves("OPEN", "buyer", "provider", lapsed=True) == ()
    assert turn("OPEN", "buyer") == "provider" and turn("AGREED", "buyer") is None


def test_every_deal_state_has_a_stage_and_every_stage_is_reachable():
    assert set(STAGE_OF_STATE) == set(State)
    used = set(STAGE_OF_STATE.values()) | set(REFINEMENTS)
    assert used == set(STAGES)


def test_stage_refinements():
    assert stage_for("NEGOTIATING", "OPEN").name == "agent_negotiating"
    assert stage_for("NEGOTIATING", None).name == "negotiating"
    assert stage_for("CAPTURED", None, True).name == "payout_issue"
    assert stage_for("CLOSED").name == "closed"  # used to read as "Waiting for PayPal"


def test_every_stage_has_its_own_panel_on_the_deal_page():
    """No stage may fall through to the catch-all 'Negotiation ended' except walked_away."""
    panels = {}
    for name in STAGES:
        deal = {"id": str(uuid.uuid4()), "stage": name, "ask": "1 USD", "approve_url": "https://x",
                "standing": {"by": "a", "price": "1", "currency": "USD"},
                "payouts": {"failed": 1, "total": 2}}
        html = render_to_string("web/_deal_move.html", {"deal": deal})
        panels[name] = re.search(r'id="h-move">([^<]+)<.*?class="lede">(.*?)</p>', html,
                                 re.S).groups()
    assert len(set(panels.values())) == len(STAGES), panels
    assert [n for n, (h, _) in panels.items() if h == "Negotiation ended"] == ["walked_away"]


@pytest.mark.parametrize("status,bucket", [
    ("SUCCEEDED", Bucket.DONE), ("SUCCESS", Bucket.DONE), ("RETURNED", Bucket.FAILED),
    ("FAILED", Bucket.FAILED), ("PENDING", Bucket.WAITING), ("ONHOLD", Bucket.WAITING),
    ("UNCLAIMED", Bucket.WAITING), ("SOMETHING_NEW", Bucket.WAITING)])
def test_payout_statuses_are_classified_once(status, bucket):
    assert classify(status) is bucket


def test_payout_summary_and_aliases():
    assert normalise("SUCCESS") == "SUCCEEDED"
    s = summarise(["SUCCEEDED", "PENDING", "RETURNED"])
    assert s == {"total": 3, "waiting": 1, "done": 1, "failed": 1, "needs_attention": True}
    assert summarise([])["needs_attention"] is False


def test_stored_webhook_status_only_claims_what_the_row_knows():
    item = "PAYMENT.PAYOUTS-ITEM.SUCCEEDED"
    assert stored_status(item, True) == "applied"
    assert stored_status(item, False) == "unapplied"
    assert stored_status("PAYMENT.CAPTURE.COMPLETED", False) == "ignored"


def test_the_docs_are_current():
    text = DOC.read_text()
    assert splice(text, reference()) == text, "run: python manage.py machines --write " \
                                              "docs/STATE_MACHINES.md"
