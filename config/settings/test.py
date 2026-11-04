from .base import *  # noqa: F403

SECRET_KEY = "test-only"
DEBUG = False
ALLOWED_HOSTS = ["testserver"]
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
PAYPAL_CLIENT_ID = "test-id"
PAYPAL_CLIENT_SECRET = "test-secret"
PAYPAL_WEBHOOK_ID = "test-webhook"
ANTHROPIC_API_KEY = ""
ANTHROPIC_MODEL = "test-model"
LLM_PROVIDER = "anthropic"
AWS_REGION = "us-east-1"
BEDROCK_MODEL_ID = "test-model"
DEMO_SUB_EMAIL = "sub@example.com"
