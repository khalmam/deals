import pytest

from agents.llm import BedrockLLM, LLMError, NoModel
from deals.management.llm_factory import llm_from_settings


class FakeBedrock:
    """Stands in for boto3's bedrock-runtime client."""

    def __init__(self, reply=None, error=None):
        self.reply, self.error, self.calls = reply, error, []

    def converse(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.reply


def answer(*texts):
    return {"output": {"message": {"role": "assistant", "content": [{"text": t} for t in texts]}}}


def test_the_request_has_the_converse_shape():
    fake = FakeBedrock(answer("hello"))
    msgs = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "{}"},
            {"role": "user", "content": "again"}]
    assert BedrockLLM(fake, "model-x", max_tokens=123).complete("be brief", msgs) == "hello"
    call = fake.calls[0]
    assert call["modelId"] == "model-x" and call["system"] == [{"text": "be brief"}]
    assert call["inferenceConfig"] == {"maxTokens": 123}
    assert call["messages"][0] == {"role": "user", "content": [{"text": "hi"}]}
    assert [m["role"] for m in call["messages"]] == ["user", "assistant", "user"]


def test_text_blocks_are_joined_and_other_blocks_ignored():
    fake = FakeBedrock(answer("a", "b"))
    fake.reply["output"]["message"]["content"].append({"toolUse": {}})
    assert BedrockLLM(fake, "m").complete("s", [{"role": "user", "content": "x"}]) == "ab"


@pytest.mark.parametrize("fake", [FakeBedrock(error=RuntimeError("throttled")),
                                  FakeBedrock(reply={}),
                                  FakeBedrock(reply={"output": {}})])
def test_any_failure_becomes_an_llm_error(fake):
    with pytest.raises(LLMError):
        BedrockLLM(fake, "m").complete("s", [{"role": "user", "content": "x"}])


def test_no_model_id_is_an_error():
    with pytest.raises(LLMError):
        BedrockLLM(FakeBedrock(), "")


def test_factory_stays_offline_without_a_key(settings):
    settings.LLM_PROVIDER, settings.ANTHROPIC_API_KEY = "anthropic", ""
    llm, who = llm_from_settings()
    assert isinstance(llm, NoModel) and "rules engine only" in who


def test_factory_builds_a_bedrock_client_from_settings(settings):
    settings.LLM_PROVIDER, settings.BEDROCK_MODEL_ID = "bedrock", "model-y"
    llm, who = llm_from_settings()
    assert isinstance(llm, BedrockLLM) and "model-y" in who
