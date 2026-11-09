"""A lifecycle as data: a table of (state, event) -> state, plus the questions every caller
asks of it. Pure: standard library only.

Services, the UI, agent menus and the docs all read the same table, so a rule is written once
and cannot drift between them."""
from dataclasses import dataclass


class IllegalTransition(Exception):
    """The event is not allowed in the current state."""


@dataclass(frozen=True, eq=False)
class Machine:
    name: str
    state_type: type  # an Enum of every state
    event_type: type  # an Enum of every event
    table: dict  # (state, event) -> next state
    initial: object

    def step(self, state, event):
        """The state after `event`, or IllegalTransition. Accepts members or their values."""
        try:
            return self.table[(self.state_type(state), self.event_type(event))]
        except KeyError:
            raise IllegalTransition(f"{event} is not allowed in state {state}") from None

    def allowed(self, state):
        """Event values that may happen next, sorted. Agent tool menus are built from this."""
        here = self.state_type(state)
        return sorted(e.value for (s, e) in self.table if s == here)

    def can(self, state, event):
        try:
            self.step(state, event)
        except IllegalTransition:
            return False
        return True

    def terminal(self):
        """States nothing can leave. A state that only loops back to itself is not terminal."""
        leaving = {s for (s, _), to in self.table.items() if to != s}
        return frozenset(s for s in self.state_type if s not in leaving)

    def is_terminal(self, state):
        return self.state_type(state) in self.terminal()

    def problems(self):
        """Structural faults in the table itself. A healthy machine returns []."""
        seen, queue = {self.initial}, [self.initial]
        while queue:
            here = queue.pop()
            for (s, _), to in self.table.items():
                if s == here and to not in seen:
                    seen.add(to)
                    queue.append(to)
        return [f"{self.name}: {s.value} is unreachable from {self.initial.value}"
                for s in self.state_type if s not in seen]

    def mermaid(self):
        """A Mermaid stateDiagram, so documentation is generated rather than maintained."""
        lines = ["stateDiagram-v2", f"    [*] --> {self.initial.value}"]
        for (s, e), to in self.table.items():
            lines.append(f"    {s.value} --> {to.value}: {e.value}")
        lines += [f"    {s.value} --> [*]" for s in self.state_type if s in self.terminal()]
        return "\n".join(lines)
