"""What the public sees of a provider's services. Floors and payout splits stay private."""
from engine.catalog import CatalogError
from engine.profile_card import card_from_services, is_bundle

LABEL_KEYS = ("name", "description", "currency")


def _bundle_view(entry):
    bundle = card_from_services([entry], require_floor=False).bundles[0]
    return {"id": bundle.id, "name": bundle.name, "currency": bundle.currency,
            "list_price": str(bundle.list_price.amount),
            "items": [{"name": i.name, "qty": i.qty, "rate": str(i.rate.amount)}
                      for i in bundle.items]}


def public_catalogue(services):
    out = []
    for entry in services if isinstance(services, list) else []:
        if is_bundle(entry):
            try:
                out.append(_bundle_view(entry))
            except CatalogError:
                continue  # a broken entry is hidden rather than shown half-parsed
        elif isinstance(entry, dict):
            out.append({k: str(entry[k])[:300] for k in LABEL_KEYS if k in entry})
    return out
