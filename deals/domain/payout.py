"""What a PayPal payout item's status means for the deal, and what became of a webhook.
Pure: standard library only.

PayPal names the same outcomes differently in webhooks (PAYMENT.PAYOUTS-ITEM.SUCCEEDED) and in
batch lookups (SUCCESS). `normalise` maps both to one word; `classify` sorts every word into
one of three buckets, so no caller compares status strings itself."""
from enum import Enum

ITEM_EVENT_PREFIX = "PAYMENT.PAYOUTS-ITEM."
LOOKUP_ALIASES = {"SUCCESS": "SUCCEEDED"}
NOT_YET = frozenset({"PENDING", "PROCESSING"})  # a lookup that says this has nothing to record
DONE = "SUCCEEDED"
FAILED = frozenset({"FAILED", "BLOCKED", "CANCELED", "DENIED", "RETURNED", "REFUNDED",
                    "REVERSED"})  # the money did not reach the sub-contractor


class Bucket(str, Enum):
    WAITING = "waiting"  # pending, or on hold / unclaimed: PayPal may still resolve it
    DONE = "done"
    FAILED = "failed"  # a person has to look at it


def normalise(status):
    return LOOKUP_ALIASES.get(status, status)


def classify(status):
    """Unknown words are WAITING, never FAILED: do not raise an alarm on a guess."""
    status = normalise(status)
    if status == DONE:
        return Bucket.DONE
    return Bucket.FAILED if status in FAILED else Bucket.WAITING


def summarise(statuses):
    """Counts for the deal page and the API, from the statuses of every payout item."""
    buckets = [classify(s) for s in statuses]
    counts = {b.value: buckets.count(b) for b in Bucket}
    return {"total": len(buckets), **counts, "needs_attention": counts["failed"] > 0}


class WebhookOutcome(str, Enum):
    APPLIED = "APPLIED"
    DUPLICATE = "DUPLICATE"  # already handled
    IGNORED = "IGNORED"  # a kind of event this app does not act on
    UNKNOWN_ITEM = "UNKNOWN_ITEM"  # a payout event for an item we have no record of


def stored_status(event_type, applied):
    """What a stored event row can honestly say about itself: 'applied', 'ignored' (not a kind
    of event this app acts on) or 'unapplied' (a payout event that matched no item yet, or
    failed half-way and awaits PayPal's retry; the row cannot tell which)."""
    if applied:
        return "applied"
    return "unapplied" if event_type.startswith(ITEM_EVENT_PREFIX) else "ignored"
