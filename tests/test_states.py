import pytest

from deals.domain.states import Event, IllegalTransition, State, allowed_events, transition


def test_happy_path_to_closed():
    s = State.DRAFT
    for e in [Event.START_NEGOTIATION, Event.TERMS_AGREED, Event.HOLD_REQUESTED,
              Event.HOLD_APPROVED, Event.DELIVERY_CONFIRMED, Event.CAPTURE_DONE,
              Event.PAYOUT_DONE, Event.INVOICE_ISSUED, Event.INVOICE_PAID]:
        s = transition(s, e)
    assert s == State.CLOSED


def test_cannot_capture_before_delivery():
    with pytest.raises(IllegalTransition):
        transition(State.HOLD_ACTIVE, Event.CAPTURE_DONE)


def test_cannot_pay_out_before_capture():
    with pytest.raises(IllegalTransition):
        transition(State.DELIVERED, Event.PAYOUT_DONE)


def test_void_allowed_while_hold_is_open():
    assert transition(State.HOLD_ACTIVE, Event.VOID) == State.VOIDED


def test_no_exit_from_closed_states():
    for s in (State.CLOSED, State.VOIDED, State.WALKED_AWAY):
        assert allowed_events(s) == []


def test_allowed_events_menu():
    assert allowed_events(State.HOLD_ACTIVE) == ["DELIVERY_CONFIRMED", "VOID"]
