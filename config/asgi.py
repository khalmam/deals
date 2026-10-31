"""ASGI entry point. Defaults to prod settings so a forgotten variable stops the app
instead of starting it in debug mode."""
import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.prod")
application = get_asgi_application()
