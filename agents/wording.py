"""What the agent may say. The model's own text is only used if it passes these checks."""
import re
from decimal import Decimal, InvalidOperation

BANNED = ("guarantee", "legally binding", "escrow", "floor", "rate card")
NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


def check_message(text):
    low = text.lower()
    return tuple(f"BANNED_WORD:{w}" for w in BANNED if w in low)


def foreign_amounts(text, allowed):
    """Amounts of 100 or more in the text that are not in `allowed` (a set of Decimals)."""
    found = []
    for raw in NUMBER.findall(text):
        m = raw.rstrip(",")  # a comma after a number is punctuation, not part of it
        try:
            value = Decimal(m.replace(",", ""))
        except InvalidOperation:
            continue
        if value >= 100 and all(value != a for a in allowed):
            found.append(f"UNLISTED_AMOUNT:{m}")
    return tuple(found)


def neutral_message(action, price, bundle_name):
    """Plain wording used whenever the model's own text is missing or not acceptable."""
    if action == "ASK":
        return f"I can offer the {bundle_name} package at {price}."
    if action == "ACCEPT":
        return f"Agreed: the {bundle_name} package at {price}."
    return "I can't go any lower than my last offer, so I will step back for now."
