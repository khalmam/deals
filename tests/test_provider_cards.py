"""The provider cards on the start and negotiate pages."""


def test_start_page_shows_provider_cards(client, parties):
    page = client.get("/start/").content.decode()
    assert "data-cards" in page and "Sample freelancer" in page


def test_negotiate_page_shows_provider_cards(client, parties):
    page = client.get("/negotiate/").content.decode()
    assert "data-cards" in page and "Available now" in page
