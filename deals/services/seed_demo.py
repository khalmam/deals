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


def _bundle(bundle_id, name, floor, *items):
    return {"id": bundle_id, "name": name, "currency": "USD", "floor": str(floor),
            "items": [dict(zip(("name", "rate", "sub_id", "sub_pct"), item)) for item in items]}


MORE = [  # (name, owner email, description, capabilities, services, approved sub-contractors)
    ("Kora Brand Studio", "hello@kora.example",
     "Brand identity and visual design for early-stage companies.",
     ["Branding", "Logo design", "Visual identity"],
     [_bundle("starter", "Brand Starter", 600, ("Logo concept and design", 700),
              ("Colour palette and type", 300)),
      _bundle("complete", "Brand Complete", 1300, ("Identity system", 1100),
              ("Brand guidelines", 600), ("Social media kit", 500))], {}),
    ("Lumen Web Works", "team@lumen.example",
     "Fast, accessible marketing sites and landing pages.",
     ["Web development", "Landing pages", "Frontend"],
     [_bundle("landing", "Landing Page", 900, ("Page design", 600), ("Build and launch", 900)),
      _bundle("site", "Marketing Site", 2300, ("Site design", 1400), ("Build", 2200),
              ("Content loading", 400))], {}),
    ("Meridian Data Labs", "labs@meridian.example",
     "Data pipelines and analytics dashboards for growing teams.",
     ["Data engineering", "Python", "Dashboards"],
     [_bundle("audit", "Data Audit", 720, ("Discovery workshop", 500),
              ("Data quality review", 700)),
      _bundle("pipeline", "Pipeline Build", 2250, ("Pipeline design", 1200),
              ("Implementation", 2000), ("Monitoring setup", 600))], {}),
    ("Atlas Content Co.", "desk@atlas.example",
     "Content strategy, copywriting and SEO, with an editor on every piece.",
     ["Copywriting", "Content strategy", "SEO"],
     [_bundle("content", "Content Pack", 1200, ("Strategy brief", 500),
              ("Four articles", 1200, "editor", 40), ("SEO review", 300))], {"editor": True}),
]


def seed_more_providers(sub_email):
    """Create the extra hosted providers once each. Returns {name: 'created' | 'exists' |
    'skipped' | 'failed: reason'}. One provider failing never stops the others, so seeding on
    every start stays safe."""
    results = {}
    for name, owner_email, description, capabilities, services, subs in MORE:
        if AgentProfile.objects.filter(name=name, agent_type="PROVIDER").exists():
            results[name] = "exists"
            continue
        if subs and not sub_email:
            results[name] = "skipped"  # its payout rules need a sub-contractor address
            continue
        try:
            register_agent(
                name=name, agent_type="PROVIDER", owner_name=name, owner_email=owner_email,
                hosted=True, description=description, capabilities=capabilities,
                services=services,
                mandate={"allow_hold": True, "allow_capture": True, "allow_void": True,
                         "allow_payouts": True,
                         "approved_subs": {sub: sub_email for sub in subs}})
            results[name] = "created"
        except Exception as exc:  # seeding is optional: report the reason, keep going
            results[name] = f"failed: {exc}"
    return results
