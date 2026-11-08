"""Read side of the negotiation protocol: how a negotiation looks to its parties."""
from django.db.models import Q

from deals.models import Negotiation, NegotiationMessage

from .negotiation_rules import NegotiationError


def role_of(neg, agent):
    if agent.pk == neg.deal.buyer_id:
        return "buyer"
    return "provider" if agent.pk == neg.deal.provider_id else None


def _view_msg(m):
    return {"proposal_id": str(m.proposal_id), "version": m.version, "type": m.msg_type,
            "in_reply_to": str(m.in_reply_to or ""), "from": m.sender.slug, "terms": m.terms,
            "terms_hash": m.terms_hash, "message_hash": m.message_hash,
            "prev_hash": m.prev_hash, "expires_at": m.expires_at, "created_at": m.created_at}


def negotiation_view(neg, created=None, replayed=False):
    neg = Negotiation.objects.select_related("deal__buyer", "deal__provider").get(pk=neg.pk)
    msgs = [_view_msg(m) for m in neg.messages.select_related("sender").order_by("version")]
    return {"negotiation_id": str(neg.pk), "status": neg.status, "deal_state": neg.deal.state,
            "buyer": neg.deal.buyer.slug, "provider": neg.deal.provider.slug,
            "deal_url": f"/deals/{neg.pk}/", "head": msgs[-1] if msgs else None,
            "standing_terms": next((m["terms"] for m in reversed(msgs) if m["terms"]), {}),
            "messages": msgs, "created": str(created or ""), "replayed": replayed}


def list_negotiations(agent, limit=50):
    mine = Q(deal__buyer=agent) | Q(deal__provider=agent)
    out = []
    for neg in Negotiation.objects.filter(mine).select_related(
            "deal__buyer", "deal__provider").order_by("-deal__created_at")[:limit]:
        head = _view_msg(NegotiationMessage.objects.select_related("sender").get(
            pk=neg.head_proposal_id))
        out.append({"negotiation_id": str(neg.pk), "status": neg.status,
                    "role": role_of(neg, agent), "buyer": neg.deal.buyer.slug,
                    "provider": neg.deal.provider.slug, "head": head})
    return out


def refresh_view(view):
    """The same negotiation, read again (a hosted provider may have answered since)."""
    return negotiation_view(Negotiation.objects.get(pk=view["negotiation_id"]),
                            view["created"], view["replayed"])


def party_view(agent, negotiation_id):
    """The negotiation as one of its parties may read it."""
    neg = Negotiation.objects.select_related("deal__buyer", "deal__provider").filter(
        pk=negotiation_id).first()
    if neg is None:
        raise NegotiationError("NOT_FOUND", "no such negotiation", 404)
    if role_of(neg, agent) is None:
        raise NegotiationError("FORBIDDEN", "you are not a party to this negotiation", 403)
    return negotiation_view(neg)
