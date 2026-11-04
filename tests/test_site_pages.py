import uuid

import pytest

from deals.models import WebhookEvent
from deals.services.open_deal import agree_terms, open_deal
from tests.test_deal_view import TERMS


@pytest.fixture
def deal(db):
    d = open_deal("Brand site", "client@example.com")
    return agree_terms(d, TERMS)


def test_health_still_answers(client):
    assert client.get("/health").json() == {"status": "up"}


def test_home_points_at_a_deal(client, deal):
    page = client.get("/").content.decode()
    assert "How it works" in page and f"/deals/{deal.pk}/" in page


def test_home_works_with_no_deals(client, db):
    assert client.get("/").status_code == 200


def test_deals_list(client, deal):
    page = client.get("/deals/").content.decode()
    assert "Brand site" in page and f"/deals/{deal.pk}/" in page


def test_receipt_page(client, deal):
    page = client.get(f"/deals/{deal.pk}/receipt/").content.decode()
    assert "Sealed receipt" in page and "Intact" in page


def test_receipt_unknown_deal_is_404(client, db):
    assert client.get(f"/deals/{uuid.uuid4()}/receipt/").status_code == 404


def test_activity_empty_then_filled(client, db):
    assert b"No PayPal events received yet" in client.get("/activity/").content
    WebhookEvent.objects.create(event_id="WH-1", event_type="PAYMENT.PAYOUTS-ITEM.SUCCEEDED",
                                resource_id="ITEM-1", applied=True)
    page = client.get("/activity/").content.decode()
    assert "PAYMENT.PAYOUTS-ITEM.SUCCEEDED" in page and "Applied" in page
