from config.env import env, env_list, parse_database_url

from .base import *  # noqa: F403

DEBUG = False
SECRET_KEY = env("SECRET_KEY", required=True)
# Render names the service's own host in RENDER_EXTERNAL_HOSTNAME, so it is allowed automatically.
ALLOWED_HOSTS = env_list("ALLOWED_HOSTS") + env_list("RENDER_EXTERNAL_HOSTNAME")
if not ALLOWED_HOSTS:
    env("ALLOWED_HOSTS", required=True)  # raises a clear ConfigError
DATABASES = {"default": parse_database_url(env("DATABASE_URL", required=True))}
PAYPAL_CLIENT_ID = env("PAYPAL_CLIENT_ID", required=True)
PAYPAL_CLIENT_SECRET = env("PAYPAL_CLIENT_SECRET", required=True)
PAYPAL_WEBHOOK_ID = env("PAYPAL_WEBHOOK_ID", required=True)
ANTHROPIC_API_KEY = env("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = env("ANTHROPIC_MODEL", "claude-sonnet-5-5")
LLM_PROVIDER = env("LLM_PROVIDER", "anthropic")  # "anthropic" or "bedrock"
AWS_REGION = env("AWS_REGION", "us-east-1")
BEDROCK_MODEL_ID = env("BEDROCK_MODEL_ID", "us.anthropic.claude-haiku-4-5-20251001-v1:0")
DEMO_SUB_EMAIL = env("DEMO_SUB_EMAIL", required=True)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
