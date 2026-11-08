"""Shared settings. No secrets and no environment reads here."""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent

INSTALLED_APPS = ["django.contrib.staticfiles", "deals", "web"]
MIDDLEWARE = ["django.middleware.security.SecurityMiddleware",
              "django.middleware.common.CommonMiddleware"]
ROOT_URLCONF = "config.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [], "APP_DIRS": True, "OPTIONS": {"context_processors": []},
}]
USE_TZ = True
TIME_ZONE = "UTC"
STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
# The public demo endpoint creates agents and PayPal holds, so it is rate limited.
UI_NEGOTIATE_WINDOW_SECONDS = 600
UI_NEGOTIATE_PER_CLIENT = 12
UI_NEGOTIATE_OVERALL = 120
PAYPAL_BASE_URL = "https://api-m.sandbox.paypal.com"  # sandbox only for this project
