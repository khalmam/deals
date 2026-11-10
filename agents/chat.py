"""Small talk for the negotiation page. When the client's message is not an offer, an
acceptance or a walk-away, the model may answer in a sentence or two. It decides nothing:
nothing is recorded, and a reply that names any price other than the current ask is dropped,
so the caller falls back to the plain hint."""
import re
from decimal import Decimal, InvalidOperation

SYSTEM = (
    "You are the freelancer's assistant in a price negotiation for a design project. "
    "The client wrote something that is not an offer, an acceptance or a walk-away. "
    "Reply in one or two friendly sentences of plain text, with no markdown and no emoji. "
    "You may greet them, answer questions about the project, and restate the current ask. "
    "Never name a price other than the current ask, never agree to a deal, never promise a "
    "discount, and never say the price can change. End by inviting them to name a price, "
    "accept the ask, or walk away."
)
NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")
MAX_CHARS = 500


def _numbers(text):
    found = set()
    for token in NUMBER.findall(text):
        try:
            found.add(Decimal(token.replace(",", "")))
        except InvalidOperation:
            pass
    return found


def _allowed(ask):
    try:
        return {Decimal(ask.split()[0])}
    except (IndexError, InvalidOperation):
        return set()


def chat_reply(llm, guard, deal_ref, text, ask="", history=""):
    """A short reply, or None when the model is unavailable or says something it must not."""
    try:
        guard.check_and_count(deal_ref)
        system = SYSTEM + (f" The current ask is {ask}." if ask else "")
        if history:
            system += (" Conversation so far:\n" + history + "\nDo not repeat a question "
                       "already asked above; answer what the client just said.")
        reply = llm.complete(system, [{"role": "user", "content": text}])
    except Exception:  # model down, over budget, odd reply: the hint is the fallback
        return None
    reply = reply.replace("**", "").lstrip("# ").strip()
    if not reply or len(reply) > MAX_CHARS or not _numbers(reply) <= _allowed(ask):
        return None
    return reply
