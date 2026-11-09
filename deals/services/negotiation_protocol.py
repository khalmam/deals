"""The negotiation protocol. Agents exchange immutable, hash-linked messages; every message
and its ledger entry commit together or not at all. Strategy belongs to the agents: this
module only authenticates, validates, orders and records."""
import uuid

from django.db import IntegrityError, transaction

from deals.domain.chain import GENESIS
from deals.domain.negotiation_machine import NEGOTIATION, Move, Status
from deals.domain.proposal import (
    MESSAGE_TYPES,
    WITH_TERMS,
    ProposalError,
    message_hash,
    parse_terms,
    request_hash,
    terms_hash,
)
from deals.domain.states import Event
from deals.models import AgentProfile, Negotiation, NegotiationMessage

from .agent_deals import AgentDealError, check_provider
from .catalogue import public_catalogue
from .common import move, utc_now
from .ledger import append
from .negotiation_effects import (
    agree_proposal,
    expiry_seconds,
    guard_own_price,
    money_of,
    plus,
)
from .negotiation_rules import Head, NegotiationError, check_turn
from .negotiation_views import negotiation_view, role_of
from .open_deal import open_deal

CLOSING = {m: NEGOTIATION.step(Status.OPEN, m).value
           for m in (Move.ACCEPT, Move.REJECT, Move.WITHDRAW)}  # message type -> final status


def _head(neg):
    m = NegotiationMessage.objects.get(pk=neg.head_proposal_id)
    role = "buyer" if m.sender_id == neg.deal.buyer_id else "provider"
    return m, Head(m.proposal_id, m.version, role, m.terms_hash)


def _replay(agent, key, rhash):
    old = NegotiationMessage.objects.filter(sender=agent, idempotency_key=key).first()
    if old is None:
        return None
    if old.request_hash != rhash:
        raise NegotiationError("IDEMPOTENCY_CONFLICT",
                               "this Idempotency-Key was used for a different request", 422)
    return negotiation_view(old.negotiation, old.proposal_id, replayed=True)


def _write(neg, sender, msg_type, in_reply_to, terms, shown, expires_at, key, rhash, now):
    """Message row, ledger entry and head update. The caller holds the transaction."""
    last = neg.messages.order_by("-version").first()
    prev = last.message_hash if last else GENESIS
    version, pid = neg.head_version + 1, uuid.uuid4()
    thash = terms_hash(terms or shown)
    mhash = message_hash(proposal_id=pid, negotiation_id=neg.pk, version=version,
                         msg_type=msg_type, in_reply_to=in_reply_to, sender=sender.pk,
                         terms_hash_=thash, expires_at=expires_at, created_at=now, prev_hash=prev)
    NegotiationMessage.objects.create(
        proposal_id=pid, negotiation=neg, version=version, msg_type=msg_type,
        in_reply_to=in_reply_to, sender=sender, terms=terms or {}, terms_hash=thash,
        prev_hash=prev, message_hash=mhash, expires_at=expires_at or "", created_at=now,
        idempotency_key=key, request_hash=rhash)
    append(neg.deal, "PROPOSAL_MADE", {
        "proposal_id": str(pid), "negotiation_id": str(neg.pk), "version": version,
        "type": msg_type, "from": sender.slug, "sender_id": str(sender.pk),
        "in_reply_to": str(in_reply_to or ""), "terms_hash": thash, "message_hash": mhash,
        "prev_hash": prev, "price": shown["price"]["amount"],
        "currency": shown["price"]["currency"]}, now)
    neg.head_version, neg.head_proposal_id = version, pid
    neg.save()
    return pid


def _close(neg, closing, by, now, reason):
    """End the negotiation with `closing` (ACCEPT, REJECT, WITHDRAW or EXPIRE)."""
    status = NEGOTIATION.step(neg.status, closing).value  # refuses to close a closed negotiation
    neg.status, neg.closed_at = status, now
    neg.save()
    append(neg.deal, "NEGOTIATION_CLOSED", {"status": status, "by": by,
                                            "negotiation_id": str(neg.pk)}, now)
    if status != Status.AGREED:
        move(neg.deal, Event.WALK_AWAY)
        neg.deal.save()
        append(neg.deal, "DEAL_WALKED_AWAY", {"by": by, "reason": reason}, now)


def _expire_if_due(neg_id, now):
    with transaction.atomic():
        neg = Negotiation.objects.select_for_update(of=("self",)).select_related(
            "deal__buyer", "deal__provider").get(pk=neg_id)
        head = NegotiationMessage.objects.get(pk=neg.head_proposal_id)
        if neg.status == Status.OPEN and head.expires_at and head.expires_at < now:
            _close(neg, Move.EXPIRE, "system", now, "the standing proposal expired")
            return True
    return False


def open_negotiation(buyer, provider_slug, raw_terms, key, body=None, now=None):
    body, now = body or {}, now or utc_now()
    if buyer.agent_type != AgentProfile.BUYER:
        raise NegotiationError("NOT_A_BUYER", "only buyer agents open negotiations", 403)
    terms, seconds = parse_terms(raw_terms), expiry_seconds(body, "PROPOSE")
    asked = {"op": "open", "provider": provider_slug, "terms": terms, "expires_in": seconds,
             "title": str(body.get("title", ""))}
    rhash = request_hash(asked)
    if (done := _replay(buyer, key, rhash)):
        return done
    provider = AgentProfile.objects.filter(slug=provider_slug, agent_type="PROVIDER",
                                           status=AgentProfile.ACTIVE).first()
    if provider is None:
        raise NegotiationError("NO_SUCH_PROVIDER", "no such provider", 404)
    try:
        check_provider(provider.services, provider.mandate, require_floor=False)
    except AgentDealError as exc:
        raise NegotiationError("PROVIDER_NOT_READY", str(exc)) from exc
    shown = {s["id"]: s for s in public_catalogue(provider.services) if "id" in s}.get(
        terms["bundle_id"])
    if shown is None or shown["currency"] != terms["price"]["currency"]:
        raise NegotiationError("UNKNOWN_BUNDLE", "the provider does not publish that bundle "
                               "in that currency", 422)
    try:
        with transaction.atomic():
            deal = open_deal(asked["title"][:200] or f"{shown['name']} from {provider.name}",
                             buyer.owner_email, now)
            deal.provider, deal.buyer, deal.bundle_id = provider, buyer, terms["bundle_id"]
            deal.save()
            neg = Negotiation.objects.create(deal=deal)
            guard_own_price(neg, buyer, "buyer", money_of(terms))
            pid = _write(neg, buyer, "PROPOSE", None, terms, terms, plus(now, seconds), key,
                         rhash, now)
    except IntegrityError:  # a concurrent retry with the same key won the race
        if (done := _replay(buyer, key, rhash)):
            return done
        raise
    return negotiation_view(neg, pid)


def submit_message(agent, negotiation_id, body, key, now=None):
    now = now or utc_now()
    neg = Negotiation.objects.select_related("deal__buyer", "deal__provider").filter(
        pk=negotiation_id).first()
    if neg is None:
        raise NegotiationError("NOT_FOUND", "no such negotiation", 404)
    role = role_of(neg, agent)
    if role is None:
        raise NegotiationError("FORBIDDEN", "you are not a party to this negotiation", 403)
    msg_type = body.get("type")
    if msg_type not in MESSAGE_TYPES:
        raise ProposalError("type must be COUNTER, ACCEPT, REJECT or WITHDRAW", "INVALID_TYPE")
    terms = parse_terms(body["terms"]) if "terms" in body else None
    seconds = expiry_seconds(body, msg_type)
    asked = {"op": "message", "negotiation": str(negotiation_id), "type": msg_type,
             "in_reply_to": str(body.get("in_reply_to", "")), "expires_in": seconds,
             "terms": terms, "terms_hash": str(body.get("terms_hash", ""))}
    rhash = request_hash({k: v for k, v in asked.items() if v is not None})
    if (done := _replay(agent, key, rhash)):
        return done
    if _expire_if_due(neg.pk, now):
        raise NegotiationError("EXPIRED", "the standing proposal expired", 410)
    try:
        with transaction.atomic():
            neg = Negotiation.objects.select_for_update(of=("self",)).select_related(
                "deal__buyer", "deal__provider").get(pk=negotiation_id)
            head_msg, head = _head(neg)
            check_turn(neg.status, head, role, msg_type, asked["in_reply_to"],
                       asked["terms_hash"], terms is not None)
            if terms and (terms["bundle_id"] != head_msg.terms["bundle_id"] or
                          terms["price"]["currency"] != head_msg.terms["price"]["currency"]):
                raise NegotiationError("SCOPE_CHANGE", "bundle and currency cannot change; "
                                       "open a new negotiation", 422)
            shown = terms or head_msg.terms
            if msg_type in WITH_TERMS or msg_type == "ACCEPT":
                guard_own_price(neg, agent, role, money_of(shown))
            expires = plus(now, seconds) if seconds else None
            pid = _write(neg, agent, msg_type, head_msg.proposal_id, terms, shown, expires,
                         key, rhash, now)
            if msg_type in CLOSING:
                if msg_type == "ACCEPT":
                    agree_proposal(neg, head_msg.terms, head_msg.proposal_id, now)
                _close(neg, msg_type, agent.slug, now, f"{agent.slug} said {msg_type}")
    except IntegrityError:
        if (done := _replay(agent, key, rhash)):
            return done
        raise NegotiationError("CONFLICT", "another message was recorded first; read the "
                               "negotiation and answer its head") from None
    return negotiation_view(neg, pid)
