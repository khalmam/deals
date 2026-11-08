import json
from decimal import Decimal

from agents.negotiating_buyer import BuyerPolicy, ProcurementAgent
from agents.negotiating_provider import ExternalProvider, ProviderPolicy
from deals.models import AgentProfile, Deal, LedgerEntry, NegotiationMessage
from tests.neg_helpers import LOCAL_FLOOR, terms

POLICY = BuyerPolicy(max_price=Decimal(1400), target_price=Decimal(1300), max_delivery_days=30,
                     min_net_days=7, max_late_fee_pct=Decimal(5))
SLUG = "amanah-procurement"


def buyer_agent(wire, parties, policy=POLICY):
    return ProcurementAgent(wire.client_for(parties["buyer_token"]), SLUG, policy)


def run_until_done(buyer, provider=None, limit=15):
    for _ in range(limit):
        if provider:
            provider.step()
        if buyer.step() == "done":
            return
    raise AssertionError("the negotiation did not finish")


def test_buyer_agent_negotiates_with_a_hosted_provider(wire, parties):
    buyer = buyer_agent(wire, parties)
    buyer.start("northstar", "standard")
    run_until_done(buyer)
    view = buyer.client.get(buyer.negotiation_id, verify=True)
    price = Decimal(view["standing_terms"]["price"]["amount"])
    assert view["status"] == "AGREED" and view["verification"]["intact"]
    assert Decimal(1037) <= price <= POLICY.max_price
    assert {m["from"] for m in view["messages"]} == {SLUG, "northstar"}
    assert view["head"]["type"] == "ACCEPT"
    deal = Deal.objects.get()
    assert deal.state == "AGREED" and deal.mandate and deal.terms["total"] == f"{price}"


def test_the_hosted_floor_never_appears_in_any_response(wire, parties):
    buyer = buyer_agent(wire, parties)
    buyer.start("northstar", "standard")
    run_until_done(buyer)
    wire.client.get("/api/agents/northstar")
    wire.client.get("/api/agents")
    assert "1037" not in "".join(wire.seen) and "floor" not in "".join(wire.seen).lower()


def test_a_lowball_gets_a_counter_not_an_error_so_the_floor_cannot_be_probed(wire, parties):
    buyer = wire.client_for(parties["buyer_token"])
    view = buyer.open("northstar", terms("900"), "lowball-key-001")
    assert view["status"] == "OPEN" and view["head"]["type"] == "COUNTER"
    assert Decimal(view["standing_terms"]["price"]["amount"]) > Decimal(1037)
    assert "floor" not in json.dumps(view).lower()


def test_retrying_open_does_not_make_the_hosted_provider_answer_twice(wire, parties):
    buyer = wire.client_for(parties["buyer_token"])
    buyer.open("northstar", terms("900"), "retry-key-0001")
    again = buyer.open("northstar", terms("900"), "retry-key-0001")
    assert again["replayed"] and NegotiationMessage.objects.count() == 2


def test_the_buyer_agent_walks_away_on_its_own_when_the_ceiling_is_too_low(wire, parties):
    poor = BuyerPolicy(max_price=Decimal(900), target_price=Decimal(800), max_delivery_days=30,
                       min_net_days=7, max_late_fee_pct=Decimal(5))
    buyer = buyer_agent(wire, parties, poor)
    buyer.start("northstar", "standard")
    run_until_done(buyer)
    view = buyer.client.get(buyer.negotiation_id)
    assert view["status"] == "REJECTED" and view["head"]["from"] == SLUG
    assert Deal.objects.get().state == "WALKED_AWAY"


def test_an_independent_provider_keeps_its_floor_to_itself(wire, parties):
    buyer = buyer_agent(wire, parties)
    provider = ExternalProvider(
        wire.client_for(parties["outside_token"]), "freelance-ext",
        ProviderPolicy(list_price=Decimal(1800), floor=Decimal(LOCAL_FLOOR)))
    buyer.start("freelance-ext", "standard")
    run_until_done(buyer, provider)
    view = buyer.client.get(buyer.negotiation_id, verify=True)
    price = Decimal(view["standing_terms"]["price"]["amount"])
    assert view["status"] == "AGREED" and view["verification"]["intact"]
    assert Decimal(LOCAL_FLOOR) <= price <= POLICY.max_price
    stored = json.dumps([
        AgentProfile.objects.get(slug="freelance-ext").services,
        list(NegotiationMessage.objects.values_list("terms", flat=True)),
        list(LedgerEntry.objects.values_list("payload", flat=True))])
    assert LOCAL_FLOOR not in stored and LOCAL_FLOOR not in "".join(wire.seen)


def test_hosted_and_external_providers_use_the_same_routes(wire, parties):
    buyer = buyer_agent(wire, parties)
    buyer.start("northstar", "standard")
    run_until_done(buyer)
    other = ProcurementAgent(wire.client_for(parties["buyer_token"]), SLUG, POLICY)
    ext = ExternalProvider(wire.client_for(parties["outside_token"]), "freelance-ext",
                           ProviderPolicy(Decimal(1800), Decimal(LOCAL_FLOOR)))
    other.start("freelance-ext", "standard")
    run_until_done(other, ext)
    assert {(m.msg_type) for m in NegotiationMessage.objects.all()} <= {
        "PROPOSE", "COUNTER", "ACCEPT"}
    assert NegotiationMessage.objects.filter(sender__slug="northstar").exists()
    assert NegotiationMessage.objects.filter(sender__slug="freelance-ext").exists()


def test_a_protocol_deal_still_renders_on_the_deal_pages(wire, parties):
    buyer = buyer_agent(wire, parties)
    buyer.start("northstar", "standard")
    run_until_done(buyer)
    nid = buyer.negotiation_id
    assert wire.client.get(f"/deals/{nid}/").status_code == 200
    assert wire.client.get(f"/api/deals/{nid}").status_code == 200
    rows = wire.client.get(f"/api/deals/{nid}").json()["transcript"]
    assert [r["who"] for r in rows][0] == SLUG and rows[-1]["message"] == "Accept"
