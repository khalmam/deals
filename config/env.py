"""The only module (besides asgi.py and manage.py) allowed to read environment variables."""
import os
from urllib.parse import unquote, urlparse


class ConfigError(RuntimeError):
    pass


def env(name, default=None, required=False):
    value = os.environ.get(name, default)
    if required and value in (None, ""):
        raise ConfigError(f"Missing required environment variable: {name}")
    return value


def env_bool(name, default=False):
    return str(env(name, str(default))).lower() in ("1", "true", "yes", "on")


def env_list(name, default=""):
    return [x.strip() for x in str(env(name, default)).split(",") if x.strip()]


def parse_database_url(url):
    """postgres://user:pass@host:port/name -> Django DATABASES entry."""
    p = urlparse(url)
    if p.scheme == "sqlite":
        return {"ENGINE": "django.db.backends.sqlite3", "NAME": p.path[1:] or ":memory:"}
    if p.scheme not in ("postgres", "postgresql"):
        raise ConfigError(f"Unsupported database scheme: {p.scheme!r}")
    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": p.path.lstrip("/"),
        "USER": unquote(p.username or ""),
        "PASSWORD": unquote(p.password or ""),
        "HOST": p.hostname or "",
        "PORT": str(p.port or 5432),
    }
