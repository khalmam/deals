"""Builds the model client the commands use, from settings. With no provider and no key the
rules engine runs alone."""
from django.conf import settings

from agents.llm import BedrockLLM, ClaudeLLM, NoModel


def llm_from_settings():
    """Returns (llm, label). LLM_PROVIDER is 'anthropic' (the default) or 'bedrock'."""
    if settings.LLM_PROVIDER == "bedrock":
        import boto3
        from botocore.config import Config

        client = boto3.client("bedrock-runtime", region_name=settings.AWS_REGION,
                              config=Config(read_timeout=20, retries={"max_attempts": 2}))
        return (BedrockLLM(client, settings.BEDROCK_MODEL_ID),
                f"Claude on Bedrock ({settings.BEDROCK_MODEL_ID})")
    key = settings.ANTHROPIC_API_KEY
    if key:
        return ClaudeLLM(key, settings.ANTHROPIC_MODEL), f"Claude ({settings.ANTHROPIC_MODEL})"
    return NoModel(), "rules engine only (no ANTHROPIC_API_KEY)"
