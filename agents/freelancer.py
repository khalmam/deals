"""The freelancer's negotiating agent. It only PROPOSES; it never decides and never raises
because of a bad model answer. The caller checks the proposal against the rules."""
from dataclasses import dataclass, replace

from .llm import LLMError
from .prompts import build_prompt
from .schema import AgentReply, ReplyError, parse_reply
from .spend_guard import BudgetExceeded
from .wording import check_message, foreign_amounts

RETRY = {"role": "user", "content": "That was not valid. Reply with one JSON object only."}


@dataclass(frozen=True)
class Proposal:
    reply: AgentReply | None
    notes: tuple = ()
    source: str = "model"  # "fallback" when there is no usable reply


class FreelancerAgent:
    def __init__(self, llm, guard):
        self.llm, self.guard = llm, guard

    def propose(self, deal_ref, ctx):
        system, messages = build_prompt(ctx)
        notes = []
        for _attempt in (1, 2):
            try:
                self.guard.check_and_count(deal_ref)
                text = self.llm.complete(system, messages)
                reply = parse_reply(text)
                break
            except BudgetExceeded:
                return Proposal(None, (*notes, "BUDGET_EXCEEDED"), "fallback")
            except LLMError:
                return Proposal(None, (*notes, "LLM_ERROR"), "fallback")
            except ReplyError:
                notes.append("PARSE_ERROR")
                messages = [*messages, {"role": "assistant", "content": text}, RETRY]
        else:
            return Proposal(None, tuple(notes), "fallback")
        allowed = {a for a in (reply.price, ctx.client_price, ctx.max_price) if a is not None}
        problems = check_message(reply.message) + foreign_amounts(reply.message, allowed)
        if problems:
            notes.extend(problems)
            reply = replace(reply, message="")
        return Proposal(reply, tuple(notes), "model")
