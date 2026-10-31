"""Deal state machine. Every money action is a transition; illegal ones raise."""
from enum import Enum


class State(str, Enum):
    DRAFT = "DRAFT"
    NEGOTIATING = "NEGOTIATING"
    AGREED = "AGREED"
    HOLD_PENDING = "HOLD_PENDING"
    HOLD_ACTIVE = "HOLD_ACTIVE"
    DELIVERED = "DELIVERED"
    CAPTURED = "CAPTURED"
    PAID_OUT = "PAID_OUT"
    INVOICED = "INVOICED"
    CLOSED = "CLOSED"
    VOIDED = "VOIDED"
    WALKED_AWAY = "WALKED_AWAY"


class Event(str, Enum):
    START_NEGOTIATION = "START_NEGOTIATION"
    TERMS_AGREED = "TERMS_AGREED"
    HOLD_REQUESTED = "HOLD_REQUESTED"
    HOLD_APPROVED = "HOLD_APPROVED"
    DELIVERY_CONFIRMED = "DELIVERY_CONFIRMED"
    CAPTURE_DONE = "CAPTURE_DONE"
    PAYOUT_DONE = "PAYOUT_DONE"
    INVOICE_ISSUED = "INVOICE_ISSUED"
    INVOICE_PAID = "INVOICE_PAID"
    CLOSE = "CLOSE"
    VOID = "VOID"
    WALK_AWAY = "WALK_AWAY"


S, E = State, Event
TRANSITIONS = {
    (S.DRAFT, E.START_NEGOTIATION): S.NEGOTIATING,
    (S.NEGOTIATING, E.TERMS_AGREED): S.AGREED,
    (S.NEGOTIATING, E.WALK_AWAY): S.WALKED_AWAY,
    (S.AGREED, E.HOLD_REQUESTED): S.HOLD_PENDING,
    (S.HOLD_PENDING, E.HOLD_APPROVED): S.HOLD_ACTIVE,
    (S.HOLD_PENDING, E.VOID): S.VOIDED,
    (S.HOLD_ACTIVE, E.DELIVERY_CONFIRMED): S.DELIVERED,
    (S.HOLD_ACTIVE, E.VOID): S.VOIDED,
    (S.DELIVERED, E.CAPTURE_DONE): S.CAPTURED,
    (S.DELIVERED, E.VOID): S.VOIDED,
    (S.CAPTURED, E.PAYOUT_DONE): S.PAID_OUT,
    (S.CAPTURED, E.INVOICE_ISSUED): S.INVOICED,
    (S.CAPTURED, E.CLOSE): S.CLOSED,
    (S.PAID_OUT, E.INVOICE_ISSUED): S.INVOICED,
    (S.PAID_OUT, E.CLOSE): S.CLOSED,
    (S.INVOICED, E.INVOICE_PAID): S.CLOSED,
}


class IllegalTransition(Exception):
    pass


def transition(state, event):
    try:
        return TRANSITIONS[(State(state), Event(event))]
    except KeyError:
        raise IllegalTransition(f"{event} is not allowed in state {state}") from None


def allowed_events(state):
    """What may happen next. The agent's tool menu is built from this."""
    return sorted(e.value for (s, e) in TRANSITIONS if s == State(state))
