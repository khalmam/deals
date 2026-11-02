"""The agent that picks the next money action. It chooses from a menu the rules built; if the
model fails or picks something else, the first safe item on the menu is used instead."""
from dataclasses import dataclass

from .llm import LLMError
from .spend_guard import BudgetExceeded
from .tools import WAIT, ChoiceError, build_prompt, parse_choice


@dataclass(frozen=True)
class Choice:
    tool: str
    reason: str
    source: str  # model, fallback or rules
    notes: tuple = ()


class ActionAgent:
    def __init__(self, llm, guard):
        self.llm, self.guard = llm, guard

    def choose(self, deal_ref, state, menu, facts):
        if menu == (WAIT,):
            return Choice(WAIT, "nothing is allowed right now", "rules")
        notes = ()
        try:
            self.guard.check_and_count(deal_ref)
            system, messages = build_prompt(state, menu, facts)
            picked = parse_choice(self.llm.complete(system, messages), menu)
            return Choice(picked.tool, picked.reason, "model")
        except BudgetExceeded:
            notes = ("BUDGET_EXCEEDED",)
        except LLMError:
            notes = ("LLM_ERROR",)
        except ChoiceError:
            notes = ("BAD_CHOICE",)
        return Choice(menu[0], "default from the rules", "fallback", notes)
