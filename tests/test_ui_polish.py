"""The new intro, the compact provider cards and the selection bar."""


def test_start_page_has_the_new_intro_and_compact_cards(client, parties):
    page = client.get("/start/").content.decode()
    assert "Choose a provider" in page and "Approve and pay with PayPal" in page
    assert "From " in page and "data-selected" in page


def test_negotiate_page_has_the_selection_bar(client, parties):
    page = client.get("/negotiate/").content.decode()
    assert "From " in page and "data-selected" in page
