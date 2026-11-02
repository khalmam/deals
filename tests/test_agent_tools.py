import json

import pytest

from agents.actor import ActionAgent
from agents.fake import FakeLLM
from agents.llm import LLMError
from agents.spend_guard import MemoryStore, SpendGuard
from agents.tools import TOOLS, WAIT, ChoiceError, build_menu, parse_choice
from deals.domain.states import allowed_events

ALL = {"allow_hold": True, "allow_capture": True, "allow_void": True, "allow_payouts": True}
NONE = dict.fromkeys(ALL, False)


def menu(state, flags=ALL, **kw):
    return build_menu(allowed_events(state), flags, **kw)


def pick(tool="capture"):
    return json.dumps({"tool": tool, "reason": "delivery is confirmed"})


def actor(replies, **guard):
    return ActionAgent(FakeLLM(replies), SpendGuard(MemoryStore(), **guard))


def test_menu_follows_the_state_machine_and_the_mandate():
    assert menu("AGREED") == ("open_hold", WAIT)
    assert menu("DELIVERED") == ("capture", WAIT)
    assert menu("CAPTURED") == ("send_payouts", WAIT)
    assert menu("AGREED", NONE) == (WAIT,)


def test_each_permission_gates_its_own_tool():
    for flag, state, tool in [("allow_hold", "AGREED", "open_hold"),
                              ("allow_capture", "DELIVERED", "capture"),
                              ("allow_payouts", "CAPTURED", "send_payouts")]:
        assert tool in menu(state)
        assert tool not in menu(state, {**ALL, flag: False})


def test_human_steps_are_never_tools():
    assert {t.event for t in TOOLS}.isdisjoint({"HOLD_APPROVED", "DELIVERY_CONFIRMED",
                                                "TERMS_AGREED", "START_NEGOTIATION"})
    assert menu("HOLD_ACTIVE") == (WAIT,)  # waiting for the client to confirm delivery
    assert menu("HOLD_PENDING") == (WAIT,)  # waiting for the client to approve on PayPal


def test_changed_terms_offer_void_and_remove_capture():
    assert menu("DELIVERED", terms_changed=True) == ("void", WAIT)
    assert menu("HOLD_ACTIVE", terms_changed=True) == ("void", WAIT)
    assert menu("HOLD_ACTIVE", {**ALL, "allow_void": False}, terms_changed=True) == (WAIT,)
    assert "void" not in menu("HOLD_ACTIVE")


def test_payouts_leave_the_menu_once_sent():
    assert menu("CAPTURED", payouts_sent=True) == (WAIT,)


def test_parse_choice_accepts_the_menu_only():
    m = ("capture", WAIT)
    assert parse_choice("```json\n" + pick() + "\n```", m).tool == "capture"
    for bad in ["no json", pick("void"), '{"tool": 5}', "[1]", '{"reason": "x"}']:
        with pytest.raises(ChoiceError):
            parse_choice(bad, m)


def test_model_choice_is_used_when_valid():
    c = actor([pick()]).choose("d", "DELIVERED", ("capture", WAIT), {})
    assert (c.tool, c.source, c.reason) == ("capture", "model", "delivery is confirmed")


def test_garbage_off_menu_outage_and_budget_all_fall_back_to_the_first_safe_item():
    m = ("capture", WAIT)
    cases = [(["oops"], "BAD_CHOICE"), ([pick("void")], "BAD_CHOICE"),
             ([LLMError("down")], "LLM_ERROR")]
    for replies, note in cases:
        c = actor(replies).choose("d", "DELIVERED", m, {})
        assert (c.tool, c.source, c.notes) == ("capture", "fallback", (note,))
    a = actor([pick(), pick()], per_deal=1)
    a.choose("d", "DELIVERED", m, {})
    assert a.choose("d", "DELIVERED", m, {}).notes == ("BUDGET_EXCEEDED",)


def test_model_is_not_asked_when_nothing_is_allowed():
    a = actor([pick()])
    c = a.choose("d", "HOLD_ACTIVE", (WAIT,), {})
    assert c.tool == WAIT and c.source == "rules" and not a.llm.calls
