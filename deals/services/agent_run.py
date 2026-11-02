from agents.tools import WAIT, build_menu
from deals.domain.mandate import Mandate
from deals.domain.states import allowed_events

from .agent_act import agent_act
from .ledger import append


def menu_for(deal, terms_changed=False):
    sent = deal.payments.filter(kind="PAYOUT_BATCH").exists()
    return build_menu(allowed_events(deal.state), Mandate.from_dict(deal.mandate).flags(),
                      sent, terms_changed)


def agent_run(deal, payments, actor, terms_changed=False, max_steps=4, now=None):
    """Let the agent take every action it is allowed to take now, then stop. It stops when it
    chooses to wait, when nothing is allowed (a human step is next), or when an action fails."""
    results = []
    for _ in range(max_steps):
        menu = menu_for(deal, terms_changed)
        pick = actor.choose(str(deal.pk), deal.state, menu, {"terms_changed": terms_changed})
        if pick.tool == WAIT:
            break
        if pick.tool not in menu:  # a misbehaving actor: record it and stop
            append(deal, "AGENT_ACTION", {"tool": pick.tool, "ok": False,
                                          "error": "not on the menu", "source": pick.source}, now)
            break
        result = agent_act(deal, payments, pick.tool, pick.reason, pick.source, now)
        results.append(result)
        if not result.ok:
            break
    return results
