from .base import *  # noqa: F403

SECRET_KEY = "test-only"
DEBUG = False
ALLOWED_HOSTS = ["testserver"]
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
PAYPAL_CLIENT_ID = "test-id"
PAYPAL_CLIENT_SECRET = "test-secret"
PAYPAL_WEBHOOK_ID = "test-webhook"
