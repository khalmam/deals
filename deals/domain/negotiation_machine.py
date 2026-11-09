"""The negotiation lifecycle and who may speak, as data. Pure: standard library only.

Two separate questions, kept separate on purpose:
  * the STATUS of a negotiation (OPEN until something closes it), and
  * the TURN inside an OPEN negotiation (the party that did not write the standing head
    answers; the author of the head may only withdraw it)."""
from enum import Enum

from .machine import Machine


class Status(str, Enum):
    OPEN = "OPEN"
    AGREED = "AGREED"
    REJECTED = "REJECTED"
    WITHDRAWN = "WITHDRAWN"
    EXPIRED = "EXPIRED"


class Move(str, Enum):
    """A message type, plus EXPIRE: the clock, which the system plays."""
    PROPOSE = "PROPOSE"  # opens a negotiation; it is the entry, not a transition
    COUNTER = "COUNTER"
    ACCEPT = "ACCEPT"
    REJECT = "REJECT"
    WITHDRAW = "WITHDRAW"
    EXPIRE = "EXPIRE"


S, M = Status, Move
TABLE = {
    (S.OPEN, M.COUNTER): S.OPEN,
    (S.OPEN, M.ACCEPT): S.AGREED,
    (S.OPEN, M.REJECT): S.REJECTED,
    (S.OPEN, M.WITHDRAW): S.WITHDRAWN,
    (S.OPEN, M.EXPIRE): S.EXPIRED,
}
NEGOTIATION = Machine("negotiation", Status, Move, TABLE, Status.OPEN)

STATUSES = tuple(s.value for s in Status)
MESSAGE_TYPES = tuple(m.value for m in Move if m is not Move.EXPIRE)

AUTHOR, OTHER = "author", "other"
# Who may send each reply, relative to the author of the standing head.
SENDER = {"COUNTER": OTHER, "ACCEPT": OTHER, "REJECT": OTHER, "WITHDRAW": AUTHOR}

BUYER, PROVIDER = "buyer", "provider"


def other_role(role):
    return PROVIDER if role == BUYER else BUYER


def is_open(status):
    return status == Status.OPEN


def legal_moves(status, head_role, role, lapsed=False):
    """Message types `role` may send now. The head was written by `head_role`.
    Empty once the negotiation is closed, or when the standing proposal has lapsed."""
    if not is_open(status) or lapsed:
        return ()
    return tuple(m for m, who in SENDER.items() if (who == AUTHOR) == (role == head_role))


def turn(status, head_role):
    """The role whose answer is awaited, or None once the negotiation is closed."""
    return other_role(head_role) if is_open(status) else None
