from agents.chat import chat_reply


class Guard:
    def check_and_count(self, ref):
        pass


class BrokenGuard:
    def check_and_count(self, ref):
        raise RuntimeError("over budget")


class Llm:
    def __init__(self, reply):
        self.reply = reply

    def complete(self, system, messages):
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


def reply(text, ask="1740.00 USD", guard=None):
    return chat_reply(Llm(text), guard or Guard(), "d1", "hello", ask)


def test_plain_greeting_passes_through():
    assert reply("Hi there! The Standard package is 1740.00 USD.") == \
        "Hi there! The Standard package is 1740.00 USD."


def test_ask_in_other_formats_is_allowed():
    assert reply("It is 1,740 for the Standard package.") is not None


def test_markdown_is_stripped():
    assert reply("# **Hello!** How can I help?") == "Hello! How can I help?"


def test_other_price_is_dropped():
    assert reply("Sure, I can do 1200 for you.") is None


def test_any_number_is_dropped_without_an_ask():
    assert reply("It costs 500.", ask="") is None


def test_model_error_gives_none():
    assert reply(RuntimeError("down")) is None


def test_guard_refusal_gives_none():
    assert reply("Hello!", guard=BrokenGuard()) is None


def test_empty_and_overlong_replies_give_none():
    assert reply("   ") is None
    assert reply("word " * 200) is None
