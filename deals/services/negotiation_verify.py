"""Cross-check the message history against the ledger and against itself."""
from deals.domain.chain import GENESIS
from deals.domain.proposal import WITH_TERMS, message_hash, terms_hash
from deals.models import LedgerEntry, Negotiation

from .ledger import verify_ledger

LINKED = ("proposal_id", "version", "type", "terms_hash", "message_hash", "prev_hash")


def _message_problems(i, m, prev_hash, prev_terms):
    out = []
    if m.version != i:
        out.append(f"message {i}: version is {m.version}")
    if m.prev_hash != prev_hash:
        out.append(f"message {i}: broken link to the previous message")
    own = terms_hash(m.terms) if m.msg_type in WITH_TERMS else prev_terms
    if m.terms_hash != own:
        out.append(f"message {i}: terms do not match their hash")
    again = message_hash(proposal_id=m.proposal_id, negotiation_id=m.negotiation_id,
                         version=m.version, msg_type=m.msg_type, in_reply_to=m.in_reply_to,
                         sender=m.sender_id, terms_hash_=m.terms_hash, expires_at=m.expires_at,
                         created_at=m.created_at, prev_hash=m.prev_hash)
    if m.message_hash != again:
        out.append(f"message {i}: contents do not match their hash")
    return out


def verify_negotiation(negotiation_id):
    """{"intact": bool, "problems": [...]}; nothing secret is ever in the problem text."""
    neg = Negotiation.objects.get(pk=negotiation_id)
    msgs = list(neg.messages.order_by("version"))
    rows = list(LedgerEntry.objects.filter(deal_id=neg.pk, kind="PROPOSAL_MADE").order_by("seq"))
    problems, prev_hash, prev_terms = [], GENESIS, ""
    if len(rows) != len(msgs):
        problems.append(f"{len(msgs)} messages but {len(rows)} ledger entries")
    for i, m in enumerate(msgs, 1):
        problems += _message_problems(i, m, prev_hash, prev_terms)
        if i <= len(rows):
            p = rows[i - 1].payload
            want = {"proposal_id": str(m.proposal_id), "version": m.version,
                    "type": m.msg_type, "terms_hash": m.terms_hash,
                    "message_hash": m.message_hash, "prev_hash": m.prev_hash}
            problems += [f"message {i}: ledger {k} differs" for k in LINKED if p.get(k) != want[k]]
        prev_hash, prev_terms = m.message_hash, m.terms_hash
    if msgs and (neg.head_version, str(neg.head_proposal_id)) != (
            msgs[-1].version, str(msgs[-1].proposal_id)):
        problems.append("the negotiation head is not the last message")
    if verify_ledger(neg.deal) is not None:
        problems.append("the ledger chain is broken")
    return {"intact": not problems, "problems": problems}
