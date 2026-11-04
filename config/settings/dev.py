from config.env import env, parse_database_url

from .base import *  # noqa: F403

DEBUG = True
SECRET_KEY = env("SECRET_KEY", "dev-insecure-key")
ALLOWED_HOSTS = ["localhost", "127.0.0.1", ".trycloudflare.com"]
DATABASES = {"default": parse_database_url(
    env("DATABASE_URL", "postgres://postgres:postgres@localhost:5432/deals"))}
PAYPAL_CLIENT_ID = env("PAYPAL_CLIENT_ID", "")
PAYPAL_CLIENT_SECRET = env("PAYPAL_CLIENT_SECRET", "")
PAYPAL_WEBHOOK_ID = env("PAYPAL_WEBHOOK_ID", "")
ANTHROPIC_API_KEY = env("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = env("ANTHROPIC_MODEL", "claude-sonnet-5-5")
LLM_PROVIDER = env("LLM_PROVIDER", "anthropic")  # "anthropic" or "bedrock"
AWS_REGION = env("AWS_REGION", "us-east-1")
BEDROCK_MODEL_ID = env("BEDROCK_MODEL_ID", "us.anthropic.claude-haiku-4-5-20251001-v1:0")
DEMO_SUB_EMAIL = env("DEMO_SUB_EMAIL", "")
