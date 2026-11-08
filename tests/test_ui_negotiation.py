import json

import pytest

from deals.models import AgentProfile, Deal, LedgerEntry


def start(client, **over):
    body = {"provider": "northstar", "bundle": "standard", "max_price": "1400",
            "target_price": "1300", **over}
    return client.post("/api/ui/negotiate", json.dumps(body), content_type="application/json")


def test_the_page_offers_only_hosted_providers(client, parties):
    page = client.get("/negotiate/").content.decode()
    assert "Northstar" in page and "Freelance Ext" not in page
    assert "Negotiate</a>" in client.get("/").content.decode()


def test_a_visitor_negotiates_in_the_browser_and_lands_on_the_deal(client, parties):
    reply = start(client)
    body = reply.json()
    assert reply.status_code == 200 and body["status"] == "AGREED"
    deal = Deal.objects.get(pk=body["negotiation_id"])
    assert deal.state == "AGREED" and deal.provider == parties["hosted"]
    page = client.get(body["deal_url"]).content.decode()
    assert "northstar" in page.lower() and "1037" not in page
    rows = client.get(f"/api/deals/{deal.pk}").json()["transcript"]
    assert rows[0]["message"] == "Propose" and rows[-1]["message"] == "Accept"


def test_the_visitors_buyer_agent_is_private_and_bounded_by_the_visitors_limit(client, parties):
    start(client, max_price="1360", target_price="1300")
    buyer = AgentProfile.objects.get(slug__startswith="visitor-")
    assert not buyer.is_public and buyer.hosted and buyer.mandate["max_deal"] == "1360"
    assert all(a["slug"] != buyer.slug for a in client.get("/api/agents").json()["results"])
    price = Deal.objects.get().terms["total"]
    assert 1037 <= float(price) <= 1360


def test_the_page_can_drive_the_deal_afterwards(client, parties):
    nid = start(client).json()["negotiation_id"]
    reply = client.post(f"/api/deals/{nid}/advance", "{}", content_type="application/json")
    assert reply.status_code != 401  # the visitor's own deal answers to the page, not a token


def test_other_agents_deals_still_need_their_token(client, parties):
    from tests.neg_helpers import Wire, terms
    wire = Wire(client)
    view = wire.client_for(parties["buyer_token"]).open("freelance-ext", terms(), "owned-0001a")
    reply = client.post(f"/api/deals/{view['negotiation_id']}/advance", "{}",
                        content_type="application/json")
    assert reply.status_code == 401


@pytest.mark.parametrize("over,words", [
    ({"provider": "freelance-ext"}, "own process"),
    ({"provider": "ghost"}, "own process"),
    ({"bundle": "nope"}, "bundle"),
    ({"max_price": "1000", "target_price": "1200"}, "above the maximum"),
    ({"max_price": "abc"}, "not a number"),
    ({"max_price": "12.5"}, "whole amount"),
    ({"max_price": "0"}, "whole amount"),
])
def test_bad_requests_get_a_plain_message(client, parties, over, words):
    reply = start(client, **over)
    assert reply.status_code == 400 and words in reply.json()["error"]
    assert Deal.objects.count() == 0


def test_a_failed_hold_is_recorded_not_hidden(client, parties, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("PayPal said no")
    monkeypatch.setattr("deals.services.negotiation_after.settle_agreement", boom)
    reply = start(client)
    assert reply.status_code == 200 and reply.json()["status"] == "AGREED"
    failure = LedgerEntry.objects.get(kind="AGENT_ACTION")
    assert failure.payload["ok"] is False and "PayPal said no" in failure.payload["error"]


def test_a_visitor_whose_limit_is_too_low_ends_without_a_deal(client, parties):
    reply = start(client, max_price="900", target_price="800")
    assert reply.status_code == 200 and reply.json()["status"] == "REJECTED"
    assert Deal.objects.get().state == "WALKED_AWAY"
