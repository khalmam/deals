import json
from decimal import Decimal

import httpx
import pytest

from agents.client_sim import Persona, ScriptedClient
from agents.fake import FakeLLM
from agents.freelancer import FreelancerAgent
from agents.llm import ClaudeLLM, LLMError
from agents.prompts import Context, build_prompt
from agents.schema import ReplyError, parse_reply
from agents.spend_guard import MemoryStore, SpendGuard
from agents.wording import check_message, foreign_amounts, neutral_message
from deals.domain.money import Money

D = Decimal
CTX = Context("Standard", ("Logo", "Illustration"), "USD", D("1740"), D("1800"), D("1200"),
              "Can you do better?", 1)


def reply(price="1760.00", message="Happy to help."):
    return json.dumps({"action": "OFFER", "price": price, "message": message})


def agent(replies, **guard):
    return FreelancerAgent(FakeLLM(replies), SpendGuard(MemoryStore(), **guard))


def test_parse_accepts_fenced_json_and_numbers_exactly():
    r = parse_reply('```json\n{"action":"OFFER","price":1700.10,"message":"hi"}\n```')
    assert r.action == "OFFER" and r.price == D("1700.10")


BAD = ["no json", '{"action":"HACK"}', '{"action":"OFFER"}', '{"action":"OFFER","price":-5}',
       '{"action":"OFFER","price":"x"}', '{"action":"OFFER","price":true}',
       '{"action":"OFFER","price":1e30}', "[1, 2]"]


@pytest.mark.parametrize("text", BAD)
def test_parse_rejects_bad_replies(text):
    with pytest.raises(ReplyError):
        parse_reply(text)


def test_wording_checks():
    assert check_message("That's my floor, a guarantee") == ("BANNED_WORD:guarantee",
                                                             "BANNED_WORD:floor")
    assert foreign_amounts("I can do 1,700 or 1500.", {D("1700")}) == ("UNLISTED_AMOUNT:1500",)
    assert foreign_amounts("net 14 days, 5% fee", set()) == ()
    for a in ("ASK", "ACCEPT", "WALK_AWAY"):
        assert check_message(neutral_message(a, Money.of(1700), "Standard")) == ()


def test_prompt_never_contains_the_floor_but_states_the_window():
    system, messages = build_prompt(CTX)
    text = system + messages[0]["content"]
    assert "1740" in text and "1800" in text and "untrusted" in text


def test_good_reply_is_used():
    p = agent([reply()]).propose("d1", CTX)
    assert p.source == "model" and p.reply.price == D("1760.00") and p.notes == ()


def test_bad_json_is_retried_once_then_recovers():
    a = agent(["oops", reply()])
    p = a.propose("d1", CTX)
    assert p.reply.price == D("1760.00") and p.notes == ("PARSE_ERROR",)
    assert len(a.llm.calls) == 2 and "not valid" in a.llm.calls[1][1][-1]["content"]


def test_two_bad_replies_fall_back():
    p = agent(["oops", "still oops"]).propose("d1", CTX)
    assert p.reply is None and p.source == "fallback"


def test_model_outage_falls_back_without_raising():
    p = agent([LLMError("down")]).propose("d1", CTX)
    assert p.reply is None and p.notes == ("LLM_ERROR",)


def test_budget_stops_calls_to_the_model():
    a = agent([reply(), reply()], per_deal=1)
    a.propose("d1", CTX)
    p = a.propose("d1", CTX)
    assert p.notes == ("BUDGET_EXCEEDED",) and len(a.llm.calls) == 1


def test_leaky_or_legal_wording_is_blanked_but_price_kept():
    p = agent([reply(message="My floor is 1500, a guarantee.")]).propose("d1", CTX)
    assert p.reply.message == "" and p.reply.price == D("1760.00")
    assert "BANNED_WORD:floor" in p.notes and "UNLISTED_AMOUNT:1500" in p.notes


def test_claude_request_shape():
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        seen["key"] = request.headers["x-api-key"]
        seen["ver"] = request.headers["anthropic-version"]
        return httpx.Response(200, json={"content": [{"type": "text", "text": "hello"}]})

    llm = ClaudeLLM("k", transport=httpx.MockTransport(handler))
    assert llm.complete("sys", [{"role": "user", "content": "hi"}]) == "hello"
    assert seen["key"] == "k" and seen["ver"] == "2023-06-01"
    assert seen["body"]["system"] == "sys" and seen["body"]["max_tokens"] == 300


def test_claude_errors_become_llm_errors():
    llm = ClaudeLLM("k", transport=httpx.MockTransport(lambda r: httpx.Response(529)))
    with pytest.raises(LLMError):
        llm.complete("s", [])
    with pytest.raises(LLMError):
        ClaudeLLM("")


def test_client_climbs_to_the_ceiling_then_takes_the_ask():
    persona = Persona("founder", Money.of(1200), Money.of(1650), seed=1)
    c = ScriptedClient(persona)
    prices = [c.next(Money.of(a), n).price for n, a in enumerate([1800, 1740, 1680, 1620])]
    assert [str(p.amount) for p in prices] == ["1200.00", "1335.00", "1429.50", "1620.00"]


def test_client_never_offers_above_the_ceiling_and_walks_when_out_of_patience():
    persona = Persona("cheap", Money.of(500), Money.of(900), patience=3)
    c = ScriptedClient(persona)
    moves = [c.next(Money.of(1800), n) for n in range(4)]
    assert all(m.price <= persona.ceiling for m in moves[:3])
    assert moves[3].action == "WALK_AWAY"
