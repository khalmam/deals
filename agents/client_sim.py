"""The simulated client. Plain rules plus a seeded choice of wording, so a demo is repeatable.
It can only make offers or walk away; it cannot move money."""
import random
from dataclasses import dataclass
from decimal import Decimal

from deals.domain.money import Money

PRESSURE = ["That's above what I planned to spend.", "Can you do a little better?",
            "My budget is tight this quarter.", "I have a quote that is lower than that."]
TAKE_IT = ["That works for me. Let's go with it.", "Fair enough, I accept that price."]


@dataclass(frozen=True)
class Persona:
    name: str
    target: Money  # the first offer
    ceiling: Money  # the most they would ever pay
    step_pct: int = 30  # how far they close the gap to the ceiling each round
    patience: int = 8  # offers they make before walking away
    seed: int = 0


@dataclass(frozen=True)
class ClientMove:
    action: str  # OFFER or WALK_AWAY
    price: Money | None
    message: str


class ScriptedClient:
    def __init__(self, persona):
        self.persona = persona
        self._last = None
        self._rng = random.Random(persona.seed)

    def _offer(self, price, lines):
        self._last = price
        return ClientMove("OFFER", price, self._rng.choice(lines))

    def next(self, ask, offers_made):
        p = self.persona
        if ask.currency != p.ceiling.currency:
            raise ValueError("currency mismatch")
        if not p.ceiling < ask:  # the ask is within their budget: take it
            return self._offer(ask, TAKE_IT)
        if offers_made >= p.patience:
            return ClientMove("WALK_AWAY", None, "This is beyond my budget, so I will pass.")
        if self._last is None:
            return self._offer(p.target, PRESSURE)
        gap = p.ceiling - self._last
        return self._offer(self._last + gap.times(Decimal(p.step_pct) / Decimal(100)), PRESSURE)
