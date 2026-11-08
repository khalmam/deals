"""The demo provider every fresh deployment starts with, so /negotiate/ works immediately."""
from deals.models import AgentProfile

from .agent_registry import register_agent

SLUG = "northstar-hosted"
BUNDLE = {"id": "standard", "name": "Standard", "currency": "USD", "floor": "1037",
          "items": [{"name": "Logo", "rate": 900},
                    {"name": "Art", "rate": 500, "sub_id": "illustrator", "sub_pct": 50},
                    {"name": "Social", "rate": 400}]}


def seed_hosted_provider(sub_email):
    """Create the hosted provider once. Returns 'created', 'exists' or 'skipped'."""
    if AgentProfile.objects.filter(slug=SLUG).exists():
        return "exists"
    if not sub_email:
        return "skipped"  # its payout rules need a sub-contractor address
    register_agent(
        name="Northstar Hosted", agent_type="PROVIDER", owner_name="Northstar",
        owner_email="owner@northstar.example", hosted=True,
        description="Backend and brand work, negotiated by a hosted agent.",
        capabilities=["Backend", "Design", "Branding"], services=[BUNDLE],
        mandate={"allow_hold": True, "allow_capture": True, "allow_void": True,
                 "allow_payouts": True, "approved_subs": {"illustrator": sub_email}})
    return "created"
