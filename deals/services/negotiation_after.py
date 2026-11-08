"""What happens after a message is recorded: a hosted provider answers, and an agreed deal gets
its PayPal hold opened. A failure here never undoes the agreement; it is written to the ledger
so the deal page and the owner can see it."""
import logging

from deals.models import Deal

from .hosted_provider import hosted_reply
from .ledger import append
from .live_deal import LiveError, settle_agreement
from .negotiation_rules import NegotiationError
from .negotiation_views import refresh_view

log = logging.getLogger(__name__)


def _note_failure(nid, exc):
    log.exception("opening the hold failed for %s", nid)
    deal = Deal.objects.filter(pk=nid).first()
    if deal is not None:
        append(deal, "AGENT_ACTION", {"tool": "open_hold", "ok": False, "source": "system",
                                      "error": f"{type(exc).__name__}: {str(exc)[:200]}"})


def after_message(view, urls_for, deps_for):
    nid = view["negotiation_id"]
    try:
        if view["status"] == "OPEN":
            view = hosted_reply(nid) or view
        if view["status"] == "AGREED":
            settle_agreement(deps_for(nid), nid, urls_for(nid))
    except (NegotiationError, LiveError) as exc:
        log.info("after-step skipped for %s: %s", nid, exc)
    except Exception as exc:
        _note_failure(nid, exc)
    return refresh_view(view)
