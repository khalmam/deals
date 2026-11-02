"""A scripted model for tests and offline demos. Replies are returned in order."""
from .llm import LLMError


class FakeLLM:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def complete(self, system, messages):
        self.calls.append((system, messages))
        if not self.replies:
            raise LLMError("no more scripted replies")
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply
