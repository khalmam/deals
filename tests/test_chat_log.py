import pytest

from deals.models import ChatMessage
from deals.services.chat_log import CAP, merge_chat, record_chat
from deals.services.deal_view import build_deal_view
from deals.services.open_deal import open_deal

pytestmark = pytest.mark.django_db


def make_deal():
    return open_deal("Brand identity", "buyer@example.com")


def test_record_saves_both_sides_after_the_last_entry():
    deal = make_deal()
    assert record_chat(deal, "hello", "Hi! The ask is 1800.00 USD.")
    rows = list(deal.chat.values_list("who", "text", "after_seq"))
    last = deal.ledger.order_by("-seq").values_list("seq", flat=True).first()
    assert rows == [("client", "hello", last), ("freelancer", "Hi! The ask is 1800.00 USD.", last)]


def test_cap_stops_saving():
    deal = make_deal()
    for _ in range(CAP // 2):
        assert record_chat(deal, "hi", "hello")
    assert not record_chat(deal, "hi", "hello")
    assert ChatMessage.objects.filter(deal=deal).count() == CAP


def test_merge_puts_chat_after_its_entry():
    deal = make_deal()
    ChatMessage.objects.create(deal=deal, after_seq=1, who="client", text="hello")
    rows = [{"seq": 0, "message": "a"}, {"seq": 1, "message": "b"}, {"seq": 2, "message": "c"}]
    out = merge_chat(rows, deal)
    assert [r["message"] for r in out] == ["a", "b", "hello", "c"]


def test_merge_without_chat_returns_rows_unchanged():
    deal = make_deal()
    rows = [{"seq": 0, "message": "a"}]
    assert merge_chat(rows, deal) == rows


def test_deal_page_data_includes_chat_in_order():
    deal = make_deal()
    record_chat(deal, "hello", "Hi there!")
    transcript = build_deal_view(deal.pk)["transcript"]
    chat = [r for r in transcript if r.get("chat")]
    assert [(r["who"], r["message"]) for r in chat] == [("Client", "hello"), ("Freelancer", "Hi there!")]


def test_ledger_is_untouched_by_chat():
    deal = make_deal()
    before = deal.ledger.count()
    record_chat(deal, "hello", "Hi there!")
    assert deal.ledger.count() == before


def test_deal_page_shows_chat_bubbles(client):
    deal = make_deal()
    record_chat(deal, "hello there", "Hi! The ask is 1800.00 USD.")
    html = client.get(f"/deals/{deal.pk}/").content.decode()
    assert "hello there" in html and "Hi! The ask is 1800.00 USD." in html
    assert 'class="client chat"' in html and 'class="freelancer chat"' in html


class Spy:
    def __init__(self, reply):
        self.reply, self.system = reply, ""

    def complete(self, system, messages):
        self.system = system
        return self.reply


class OkGuard:
    def check_and_count(self, ref):
        pass


def test_recent_turns_are_in_order():
    from deals.services.chat_log import recent_turns
    deal = make_deal()
    record_chat(deal, "hello", "Hi! Ready to go ahead?")
    lines = recent_turns(deal).split("\n")
    assert lines[-2:] == ["Client: hello", "Freelancer: Hi! Ready to go ahead?"]


def test_history_reaches_the_intent_reader():
    from agents.intent import read_intent
    spy = Spy('{"action": "ACCEPT", "price": null}')
    out = read_intent(spy, OkGuard(), "d1", "Yes", "1650.00 USD", "Freelancer: Ready at 1650?")
    assert "Conversation so far" in spy.system and "Ready at 1650?" in spy.system
    assert out.action == "ACCEPT"


def test_history_reaches_the_chat_reply():
    from agents.chat import chat_reply
    spy = Spy("Happy to help.")
    chat_reply(spy, OkGuard(), "d1", "hi", "1650.00 USD", "Client: hello")
    assert "Client: hello" in spy.system and "Do not repeat" in spy.system
