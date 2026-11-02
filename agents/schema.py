"""The structured reply the model must give. Parsing is strict; anything odd is an error."""
import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

ACTIONS = ("OFFER", "ACCEPT", "WALK_AWAY")
MAX_MESSAGE = 280
MAX_PRICE = Decimal("100000000")


class ReplyError(ValueError):
    pass


@dataclass(frozen=True)
class AgentReply:
    action: str
    price: Decimal | None
    message: str


def _extract_json(text):
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ReplyError("no JSON object found")
    return text[start:end + 1]


def _parse_price(raw):
    if raw is None:
        return None
    if isinstance(raw, bool) or not isinstance(raw, int | Decimal | str):
        raise ReplyError("price must be a number or a string")
    try:
        price = Decimal(str(raw))
    except InvalidOperation as exc:
        raise ReplyError("price is not a number") from exc
    if not price.is_finite() or not 0 < price <= MAX_PRICE:
        raise ReplyError("price is out of range")
    return price


def parse_reply(text):
    try:
        data = json.loads(_extract_json(text), parse_float=Decimal)
    except json.JSONDecodeError as exc:
        raise ReplyError("not valid JSON") from exc
    if not isinstance(data, dict) or data.get("action") not in ACTIONS:
        raise ReplyError("missing or unknown action")
    price = _parse_price(data.get("price"))
    if data["action"] == "OFFER" and price is None:
        raise ReplyError("an OFFER needs a price")
    return AgentReply(data["action"], price, str(data.get("message", ""))[:MAX_MESSAGE])
