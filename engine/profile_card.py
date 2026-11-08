"""Builds a rate card from the plain dicts an agent publishes in its profile. Pure."""
from deals.domain.money import Money, MoneyError

from .catalog import Bundle, CatalogError, LineItem, RateCard


def _money(value, currency):
    return Money.of(str(value), currency)  # str() keeps JSON numbers exact


def _item(raw, currency):
    return LineItem(str(raw["name"]), _money(raw["rate"], currency), int(raw.get("qty", 1)),
                    raw.get("sub_id") or None, int(raw.get("sub_pct", 0)))


def _bundle(raw):
    currency = str(raw.get("currency", "USD"))
    items = tuple(_item(i, currency) for i in raw["items"])
    return Bundle(str(raw["id"]), str(raw.get("name", raw["id"])), items,
                  _money(raw.get("floor", 0), currency))  # no floor published: zero


def is_bundle(entry):
    return isinstance(entry, dict) and {"id", "items"} <= entry.keys()


def card_from_services(services, require_floor=True):
    """Entries without id and items are descriptions only and are skipped. A floor is
    optional: a provider that keeps its floor in its own agent publishes none."""
    try:
        bundles = tuple(_bundle(s) for s in services or [] if is_bundle(s))
    except (KeyError, TypeError, ValueError, MoneyError) as exc:
        raise CatalogError(f"the published rate card is invalid: {exc}") from exc
    if require_floor:
        unpriced = [s["id"] for s in services if is_bundle(s) and "floor" not in s]
        if unpriced:
            raise CatalogError(f"{unpriced[0]}: no floor is published, so this provider "
                               "negotiates only through /api/negotiations")
    if not bundles:
        raise CatalogError("this agent has not published a rate card")
    return RateCard(bundles=bundles)
