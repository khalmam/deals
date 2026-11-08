"""Who may say what, and when. Plain values in, errors out: no database access here."""
from collections import namedtuple

from deals.domain.proposal import WITH_TERMS

Head = namedtuple("Head", "proposal_id version role terms_hash")


class NegotiationError(Exception):
    """A refusal that is safe to show the calling agent. Never carries a private number."""

    def __init__(self, code, message, status=409, **extra):
        super().__init__(message)
        self.code, self.status, self.extra = code, status, extra


def check_turn(status, head, role, msg_type, in_reply_to, claimed_hash, has_terms):
    if status != "OPEN":
        raise NegotiationError("CLOSED", f"this negotiation is {status.lower()}")
    if msg_type == "PROPOSE":
        raise NegotiationError("ALREADY_OPEN", "a negotiation opens with one PROPOSE; "
                               "reply with COUNTER, ACCEPT, REJECT or WITHDRAW")
    if str(in_reply_to) != str(head.proposal_id):
        raise NegotiationError("STALE", "in_reply_to is not the current head",
                               head=str(head.proposal_id), head_version=head.version)
    if msg_type in WITH_TERMS and not has_terms:
        raise NegotiationError("TERMS_REQUIRED", "a COUNTER carries a full set of terms", 400)
    if msg_type not in WITH_TERMS and has_terms:
        raise NegotiationError("TERMS_NOT_ALLOWED", f"{msg_type} cannot carry terms; it answers "
                               "the head exactly as it stands", 400)
    if msg_type == "WITHDRAW":
        if role != head.role:
            raise NegotiationError("NOT_YOUR_PROPOSAL", "only the author can withdraw it")
    elif role == head.role:
        raise NegotiationError("NOT_YOUR_TURN", "wait for the other party to answer")
    if msg_type == "ACCEPT" and claimed_hash != head.terms_hash:
        raise NegotiationError("TERMS_MISMATCH", "terms_hash is not the current head's", 409,
                               head_terms_hash=head.terms_hash)
