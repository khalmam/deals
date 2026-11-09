"""Where a deal stands for the person or agent looking at it, and what they can do next.
Pure: standard library only.

The deal's State (12 values) is the authority. A Stage is a *view* of it, derived by one table,
so the page, the JSON API and the docs all say the same thing. Nothing here is stored."""
from dataclasses import dataclass

from .negotiation_machine import Status
from .states import State


@dataclass(frozen=True)
class Action:
    name: str
    method: str = "POST"
    path: str | None = ""  # under /api/deals/<id>; None means the deal's PayPal approve link


@dataclass(frozen=True)
class Stage:
    name: str
    waiting_on: str  # client, agents, agent, paypal, owner or nobody
    actions: tuple = ()


ADVANCE = Action("advance", "POST", "/advance")
REFRESH = Action("refresh", "POST", "/refresh")
STAGES = {s.name: s for s in (
    Stage("negotiating", "client", (Action("offer", "POST", "/offers"),)),
    Stage("agent_negotiating", "agents"),  # buyer and provider agents talk via /api/negotiations
    Stage("agreed", "agent", (ADVANCE,)),
    Stage("approval", "client", (Action("approve_hold", "GET", None),)),
    Stage("held", "client", (Action("confirm_delivery", "POST", "/delivery"),
                             Action("cancel", "POST", "/cancel"))),
    Stage("delivered", "agent", (ADVANCE,)),
    Stage("captured", "paypal", (REFRESH,)),
    Stage("payout_issue", "owner", (REFRESH,)),  # a payout failed: a person has to look
    Stage("paid", "nobody"),
    Stage("invoiced", "client"),
    Stage("closed", "nobody"),
    Stage("voided", "nobody"),
    Stage("walked_away", "nobody"),
)}

S = State
STAGE_OF_STATE = {
    S.DRAFT: "negotiating", S.NEGOTIATING: "negotiating", S.AGREED: "agreed",
    S.HOLD_PENDING: "approval", S.HOLD_ACTIVE: "held", S.DELIVERED: "delivered",
    S.CAPTURED: "captured", S.PAID_OUT: "paid", S.INVOICED: "invoiced", S.CLOSED: "closed",
    S.VOIDED: "voided", S.WALKED_AWAY: "walked_away",
}


# Stages that refine a state rather than map to one (see stage_for), for the docs.
REFINEMENTS = {"agent_negotiating": "NEGOTIATING, while an agent-to-agent negotiation is OPEN",
               "payout_issue": "CAPTURED, while any payout item has failed"}


def stage_for(state, negotiation_status=None, payout_needs_attention=False):
    """The Stage for a deal. Two facts the State alone cannot carry refine it:
    an agent-to-agent negotiation still OPEN, and a captured deal with a failed payout."""
    state = State(state)
    if state is S.NEGOTIATING and negotiation_status == Status.OPEN:
        return STAGES["agent_negotiating"]
    if state is S.CAPTURED and payout_needs_attention:
        return STAGES["payout_issue"]
    return STAGES[STAGE_OF_STATE[state]]
