from datetime import datetime, timezone

from deals.domain.states import transition


def utc_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def move(deal, event):
    deal.state = transition(deal.state, event).value
