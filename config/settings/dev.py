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
