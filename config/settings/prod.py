from config.env import env, env_list, parse_database_url

from .base import *  # noqa: F403

DEBUG = False
SECRET_KEY = env("SECRET_KEY", required=True)
ALLOWED_HOSTS = env_list("ALLOWED_HOSTS") or env("ALLOWED_HOSTS", required=True)
DATABASES = {"default": parse_database_url(env("DATABASE_URL", required=True))}
PAYPAL_CLIENT_ID = env("PAYPAL_CLIENT_ID", required=True)
PAYPAL_CLIENT_SECRET = env("PAYPAL_CLIENT_SECRET", required=True)
PAYPAL_WEBHOOK_ID = env("PAYPAL_WEBHOOK_ID", required=True)
ANTHROPIC_API_KEY = env("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = env("ANTHROPIC_MODEL", "claude-sonnet-5-5")
