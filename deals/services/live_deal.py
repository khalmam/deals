"""The live flow the web layer calls. Each function takes the deal id, does one step and
returns plain data. Collaborators come in as Deps, so tests can pass fakes."""
from dataclasses import dataclass
from functools import wraps

from agents.chat import chat_reply
from agents.intent import read_intent
from deals.domain.mandate import MandateViolation
from deals.domain.money import Money, MoneyError
from deals.domain.states import IllegalTransition
from deals.models import Deal, Negotiation

from .agent_act import URLS
from .agent_deals import AgentDealError, check_budget
from .agent_run import agent_run
from .chat_log import recent_turns, record_chat
from .confirm_hold import TermsMismatch, confirm_hold
from .deal_view import DealNotFound
from .delivery_capture_void import confirm_delivery, void
from .ledger import append
from .mandate import set_mandate
from .negotiate_round import NegotiationClosed, current_ask, play_round, start_negotiation
from .open_deal import open_deal
from .refresh_payouts import refresh_payouts
from .send_payouts import PayoutsAlreadySent, settle_without_payouts

HINT = "Name a price you would pay, accept the current ask, or say you are walking away."
ERRORS = (IllegalTransition, MandateViolation, TermsMismatch, PayoutsAlreadySent,
          NegotiationClosed, MoneyError, AgentDealError)


class LiveError(Exception):
    """A step the rules refused. The message is safe to show the visitor."""


@dataclass(frozen=True)
class Deps:
    card: object
    freelancer: object
    actor: object
    guard: object
    llm: object
    payments: object
    mandate: object
    bundle_id: str = "standard"


def _guarded(fn):
    @wraps(fn)
    def inner(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except ERRORS as exc:
            raise LiveError(str(exc)) from exc
    return inner


def _deal(deal_id):
    deal = Deal.objects.filter(pk=deal_id).first()
    if deal is None:
        raise DealNotFound(str(deal_id))
    return deal


def start_deal(deps, title="Brand identity", client_email="buyer@personal.example.com",
               now=None):
    deal = open_deal(title, client_email, now)
    start_negotiation(deal, deps.card, deps.bundle_id, now)
    return str(deal.pk)


@_guarded
def say(deps, deal_id, text, urls=URLS, now=None):
    deal = _deal(deal_id)
    if Negotiation.objects.filter(pk=deal.pk).exists():
        raise AgentDealError("this deal negotiates through /api/negotiations", 409)
    ask = current_ask(deal)
    label = f"{ask.amount} {ask.currency}" if ask else ""
    history = recent_turns(deal)
    intent = read_intent(deps.llm, deps.guard, str(deal.pk), text, label,
                         history)
    if intent.action == "UNCLEAR":
        reply = (chat_reply(deps.llm, deps.guard, str(deal.pk), text, label, history)
                 if intent.source == "model" else None)
        if reply:
            record_chat(deal, text, reply)
        return {"status": "UNCLEAR", "message": reply or HINT, "chat": bool(reply)}
    if ask and intent.action in ("OFFER", "ACCEPT"):
        offer = ask if intent.action == "ACCEPT" else Money.of(intent.price, ask.currency)
        check_budget(deal, offer)
    out = play_round(deal, deps.card, deps.bundle_id, deps.freelancer, intent.action,
                     intent.price, text, now=now)
    if out.status == "AGREED":
        set_mandate(deal, deps.mandate, now)
        agent_run(deal, deps.payments, deps.actor, urls=urls, now=now)  # opens the hold
    return {"status": out.status, "read_by": intent.source}


@_guarded
def advance(deps, deal_id, urls=URLS, now=None):
    """Let the agent take whatever step is allowed next (the hold, or the capture)."""
    deal = _deal(deal_id)
    agent_run(deal, deps.payments, deps.actor, urls=urls, now=now)
    settle_without_payouts(deal, now)  # a captured deal with no sub-contractor is finished
    return {"state": deal.state}


@_guarded
def approve_return(deps, deal_id, now=None):
    """PayPal sent the buyer back after approving: authorize and check the terms hash."""
    deal = _deal(deal_id)
    try:
        confirm_hold(deal, deps.payments, now)
    except TermsMismatch as exc:  # PayPal's hold was released; leave a trace, not a silent page
        append(deal, "AGENT_ACTION", {"tool": "confirm_hold", "ok": False, "source": "system",
                                      "error": str(exc)[:200]}, now)
        raise
    return {"state": deal.state}


@_guarded
def deliver(deps, deal_id, now=None):
    deal = _deal(deal_id)
    confirm_delivery(deal, "client", now)
    agent_run(deal, deps.payments, deps.actor, now=now)  # captures, then pays the sub-contractor
    settle_without_payouts(deal, now)  # no sub-contractor owed: nothing left to wait for
    refresh_payouts(deal, deps.payments, now)
    return {"state": deal.state}


@_guarded
def cancel(deps, deal_id, now=None):
    """The terms changed: the agent is shown that and should void. If it does not, we void."""
    deal = _deal(deal_id)
    done = agent_run(deal, deps.payments, deps.actor, terms_changed=True, now=now)
    if not any(r.ok and r.tool == "void" for r in done):
        void(deal, deps.payments, now)
    return {"state": deal.state}


@_guarded
def refresh(deps, deal_id, now=None):
    deal = _deal(deal_id)
    changed = refresh_payouts(deal, deps.payments, now)
    settle_without_payouts(deal, now)  # also unsticks a deal captured before this fix
    return {"changed": changed, "state": deal.state}


@_guarded
def settle_agreement(deps, deal_id, urls=URLS, now=None):
    """After a negotiation ends AGREED: record the provider's mandate and let the agent open
    the PayPal hold. Safe to call twice; it acts only while the deal is still AGREED."""
    deal = _deal(deal_id)
    if deal.state != "AGREED":
        return {"state": deal.state}
    if not deal.mandate:
        set_mandate(deal, deps.mandate, now)
    agent_run(deal, deps.payments, deps.actor, urls=urls, now=now)
    return {"state": deal.state}
