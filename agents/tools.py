"""The money actions the agent may choose. Pure. The menu is built from the state machine's
allowed events and the owner's mandate, so the model can only pick what is legal right now.
Approving the hold, confirming delivery and agreeing terms are never tools: they stay human."""
import json
from dataclasses import dataclass

WAIT = "wait"


@dataclass(frozen=True)
class Tool:
    name: str
    event: str  # the state-machine event it performs
    needs: str  # the mandate permission it requires
    help: str


TOOLS = (
    Tool("void", "VOID", "allow_void",
         "Release the hold. Only offered when the agreed terms have changed."),
    Tool("open_hold", "HOLD_REQUESTED", "allow_hold",
         "Ask PayPal to hold the agreed total and send the client the approval link."),
    Tool("capture", "CAPTURE_DONE", "allow_capture",
         "Take the held money. Only possible after the client confirmed delivery."),
    Tool("send_payouts", "PAYOUT_DONE", "allow_payouts",
         "Pay the approved sub-contractors their shares of the captured money."),
)
BY_NAME = {t.name: t for t in TOOLS}


class ChoiceError(ValueError):
    pass


@dataclass(frozen=True)
class Picked:
    tool: str
    reason: str


def build_menu(allowed_events, flags, payouts_sent=False, terms_changed=False):
    """Tool names the agent may pick right now, safest first, with 'wait' always last."""
    menu = []
    for t in TOOLS:
        if t.event not in allowed_events or not flags.get(t.needs):
            continue
        if (t.name == "void") != terms_changed:  # changed terms: void only; otherwise never void
            continue
        if t.name == "send_payouts" and payouts_sent:
            continue
        menu.append(t.name)
    return (*menu, WAIT)


SYSTEM = """You act for a freelancer who set rules for you. Choose ONE next action.
Reply with one JSON object and nothing else:
{"tool": "<a name from the menu>", "reason": "one short sentence"}
Choose "wait" when nothing should happen yet. Never choose a name that is not on the menu."""


def build_prompt(state, menu, facts):
    lines = [f"Deal state: {state}", f"Facts: {json.dumps(facts, sort_keys=True)}", "Menu:"]
    lines += [f"- {n}: {BY_NAME[n].help}" if n in BY_NAME else f"- {n}: do nothing for now"
              for n in menu]
    return SYSTEM, [{"role": "user", "content": "\n".join(lines)}]


def parse_choice(text, menu):
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ChoiceError("no JSON object found")
    try:
        data = json.loads(text[start:end + 1])
    except json.JSONDecodeError as exc:
        raise ChoiceError("not valid JSON") from exc
    tool = data.get("tool") if isinstance(data, dict) else None
    if tool not in menu:
        raise ChoiceError("tool is not on the menu")
    return Picked(tool, str(data.get("reason", ""))[:200])
