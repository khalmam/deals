"""Every lifecycle in one place, and the generated reference for docs/STATE_MACHINES.md.
Pure: standard library only."""
from .negotiation_machine import NEGOTIATION
from .payout import DONE, FAILED, NOT_YET
from .stage import REFINEMENTS, STAGE_OF_STATE, STAGES
from .states import DEAL

ALL = (DEAL, NEGOTIATION)  # the machines with real transitions
START, END = "<!-- machines:start -->", "<!-- machines:end -->"


def _actions(stage):
    return ", ".join(f"`{a.method} {'<approve_url>' if a.path is None else a.path}`"
                     for a in stage.actions) or "none"


def reference():
    """The generated block of the docs: diagrams, the stage table and the payout buckets."""
    out = []
    for m in ALL:
        out += [f"#### `{m.name}`", "", "```mermaid", m.mermaid(), "```", ""]
    out += ["#### Stages (what the deal page and `GET /api/deals/<id>` show)", "",
            "| Stage | Deal states | Waiting on | Next actions |", "|---|---|---|---|"]
    for st in STAGES.values():
        states = [s.value for s, name in STAGE_OF_STATE.items() if name == st.name]
        where = ", ".join(states) if states else REFINEMENTS[st.name]
        out.append(f"| `{st.name}` | {where} | {st.waiting_on} | {_actions(st)} |")
    out += ["", "#### Payout item statuses", "",
            f"- done: `{DONE}`",
            f"- failed (a person must look): {', '.join(f'`{s}`' for s in sorted(FAILED))}",
            f"- not yet, nothing to record: {', '.join(f'`{s}`' for s in sorted(NOT_YET))}",
            "- anything else (on hold, unclaimed, unknown): waiting"]
    return "\n".join(out)
