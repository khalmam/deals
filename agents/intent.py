"""Reads one free-text message from the client. The model only labels what the person meant
(an offer, an acceptance, walking away); it decides nothing. If the model is down, over budget
or answers badly, plain rules read the message instead, so a demo never stalls."""
import json
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

ACTIONS = ("OFFER", "ACCEPT", "WALK_AWAY", "UNCLEAR")
SYSTEM = (
    "You read one message from a client negotiating the price of a design project. "
    "Reply with JSON only, no other text: "
    '{"action": "OFFER" | "ACCEPT" | "WALK_AWAY" | "UNCLEAR", "price": number or null}. '
    "OFFER: the client names a price they would pay, in any wording (twelve hundred, 1.5k, "
    "1,300); put it in price as plain dollars. ACCEPT: the client agrees to the seller's "
    "current ask. WALK_AWAY: the client leaves or refuses to go on. UNCLEAR: anything else, "
    "including questions. Never invent a price."
)
NUM = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(k\b)?", re.I)
WALK = re.compile(r"\b(walk|pass|forget it|no deal|not interested|i'?m out|cancel)\b", re.I)
YES = re.compile(r"\b(accept|deal|agreed|ok|okay|yes|sure|fine|works for me)\b", re.I)


@dataclass(frozen=True)
class Intent:
    action: str  # OFFER, ACCEPT, WALK_AWAY or UNCLEAR
    price: Decimal | None
    source: str  # model or rules


def _price(value):
    try:
        price = Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None
    return price if price > 0 else None


def read_by_rules(text):
    found = NUM.search(text)
    if found:
        value = Decimal(found.group(1).replace(",", ""))
        price = _price(value * 1000 if found.group(2) else value)
        if price:
            return Intent("OFFER", price, "rules")
    if WALK.search(text):
        return Intent("WALK_AWAY", None, "rules")
    if YES.search(text):
        return Intent("ACCEPT", None, "rules")
    return Intent("UNCLEAR", None, "rules")


def read_intent(llm, guard, deal_ref, text, ask="", history=""):
    try:
        guard.check_and_count(deal_ref)
        system = SYSTEM + f" The seller's current ask is {ask}." if ask else SYSTEM
        if history:
            system += (" Conversation so far:\n" + history + "\nRead the message in that "
                       "context: if the seller just asked whether to go ahead at the current "
                       "ask, a plain yes or I am ready is ACCEPT and a plain no is WALK_AWAY.")
        raw = llm.complete(system, [{"role": "user", "content": text}])
        data = json.loads(raw[raw.index("{"):raw.rindex("}") + 1])
        action = data["action"]
        if action not in ACTIONS:
            raise ValueError(action)
        price = _price(data.get("price"))
        if action == "OFFER" and price is None:
            raise ValueError("an offer needs a price")
        return Intent(action, price if action == "OFFER" else None, "model")
    except Exception:  # any model failure falls back to the rules reader
        return read_by_rules(text)
