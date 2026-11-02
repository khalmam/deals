from dataclasses import dataclass

from agents.tools import BY_NAME
from deals.domain.mandate import Mandate, MandateViolation
from deals.domain.states import Event, IllegalTransition, transition

from .confirm_hold import TermsMismatch
from .delivery_capture_void import capture, void
from .ledger import append
from .open_hold import open_hold
from .send_payouts import PayoutsAlreadySent, send_payouts

URLS = ("https://example.com/ok", "https://example.com/no")
REFUSALS = (IllegalTransition, MandateViolation, PayoutsAlreadySent, TermsMismatch)


@dataclass(frozen=True)
class ActionResult:
    tool: str
    ok: bool
    detail: str = ""


def _run(tool, deal, payments, urls, now):
    if tool == "open_hold":
        return open_hold(deal, payments, urls[0], urls[1], now)
    if tool == "capture":
        return capture(deal, payments, now)
    if tool == "void":
        return void(deal, payments, now)
    return send_payouts(deal, payments, actor="agent", now=now)


def _ids(deal, tool):
    if tool == "open_hold":
        return {"order_id": deal.order_id}
    if tool == "void":
        return {"auth_id": deal.auth_id}
    kind = "CAPTURE" if tool == "capture" else "PAYOUT_BATCH"
    rec = deal.payments.filter(kind=kind).first()
    return {"capture_id" if tool == "capture" else "batch_id": rec.paypal_id if rec else ""}


def agent_act(deal, payments, tool, reason="", source="model", now=None, urls=URLS):
    """Do one money action for the agent, only if the state and the mandate allow it.
    Allowed or refused, the attempt is written to the ledger."""
    spec = BY_NAME.get(tool)
    try:
        if spec is None:
            raise MandateViolation(f"{tool!r} is not a tool")
        transition(deal.state, Event(spec.event))  # refuse before touching PayPal
        if not Mandate.from_dict(deal.mandate).flags().get(spec.needs):
            raise MandateViolation(f"the mandate does not allow {tool}")
        _run(tool, deal, payments, urls, now)
    except REFUSALS as exc:
        append(deal, "AGENT_ACTION", {"tool": tool, "ok": False, "error": str(exc),
                                      "why": reason, "source": source}, now)
        return ActionResult(tool, False, str(exc))
    append(deal, "AGENT_ACTION", {"tool": tool, "ok": True, **_ids(deal, tool),
                                  "why": reason, "source": source}, now)
    return ActionResult(tool, True)
