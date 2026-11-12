import importlib
import sys

import pytest
import yaml
from django.core.management import call_command
from django.test import override_settings

from config.env import ConfigError
from deals.models import AgentProfile
from deals.services.seed_demo import seed_hosted_provider
from web import ratelimit

PROD_ENV = {"SECRET_KEY": "x", "DATABASE_URL": "postgres://u:p@h:5432/d", "PAYPAL_CLIENT_ID": "i",
            "PAYPAL_CLIENT_SECRET": "s", "PAYPAL_WEBHOOK_ID": "w", "DEMO_SUB_EMAIL": "a@b.co"}


def load_prod(monkeypatch, **env):
    for key in ("ALLOWED_HOSTS", "RENDER_EXTERNAL_HOSTNAME"):
        monkeypatch.delenv(key, raising=False)
    for key, value in {**PROD_ENV, **env}.items():
        monkeypatch.setenv(key, value)
    sys.modules.pop("config.settings.prod", None)
    return importlib.import_module("config.settings.prod")


def test_healthz_answers_when_the_database_does(client, db):
    reply = client.get("/healthz")
    assert reply.status_code == 200 and reply.json() == {"ok": True}


def test_prod_trusts_the_hostname_render_provides(monkeypatch):
    prod = load_prod(monkeypatch, RENDER_EXTERNAL_HOSTNAME="deals-ab12.onrender.com")
    assert prod.ALLOWED_HOSTS == ["deals-ab12.onrender.com"]
    both = load_prod(monkeypatch, ALLOWED_HOSTS="deals.example.org",
                     RENDER_EXTERNAL_HOSTNAME="deals-ab12.onrender.com")
    assert both.ALLOWED_HOSTS == ["deals.example.org", "deals-ab12.onrender.com"]


def test_prod_refuses_to_start_with_no_host(monkeypatch):
    with pytest.raises(ConfigError):
        load_prod(monkeypatch)


def test_the_blueprint_matches_what_prod_requires():
    blueprint = yaml.safe_load(open("render.yaml"))
    service = blueprint["services"][0]
    keys = {v["key"] for v in service["envVars"]}
    assert {"SECRET_KEY", "DATABASE_URL", "PAYPAL_CLIENT_ID", "PAYPAL_CLIENT_SECRET",
            "PAYPAL_WEBHOOK_ID", "DEMO_SUB_EMAIL", "DJANGO_SETTINGS_MODULE"} <= keys
    assert service["healthCheckPath"] == "/healthz"
    assert "migrate" in service["startCommand"] and "$PORT" in service["startCommand"]
    secrets = [v for v in service["envVars"] if v["key"].startswith("PAYPAL_CLIENT")]
    assert all(v.get("sync") is False and "value" not in v for v in secrets)


def test_seeding_is_idempotent_and_needs_the_sub_email(db):
    assert seed_hosted_provider("") == "skipped"
    assert seed_hosted_provider("sub@example.com") == "created"
    assert seed_hosted_provider("sub@example.com") == "exists"
    provider = AgentProfile.objects.get(slug="northstar-hosted")
    assert provider.hosted and provider.mandate["approved_subs"]["illustrator"]


def test_the_seed_command_reports_what_it_did(db, capsys):
    call_command("seed_demo")
    call_command("seed_demo")
    lines = capsys.readouterr().out.split("\n")  # the extra providers print their own lines
    assert [ln for ln in lines if ln.startswith("demo provider:")] == ["demo provider: created",
                                                       "demo provider: exists"]


def test_the_public_endpoint_is_rate_limited(client, parties):
    import json
    body = json.dumps({"provider": "northstar", "bundle": "standard", "max_price": "1400",
                       "target_price": "1300"})
    ratelimit.reset()
    with override_settings(UI_NEGOTIATE_PER_CLIENT=2, UI_NEGOTIATE_OVERALL=100):
        codes = [client.post("/api/ui/negotiate", body, content_type="application/json").status_code
                 for _ in range(3)]
        reply = client.post("/api/ui/negotiate", body, content_type="application/json")
    ratelimit.reset()
    assert codes == [200, 200, 429] and int(reply["Retry-After"]) > 0


def test_the_overall_cap_protects_the_demo_from_many_clients(client, parties):
    import json
    body = json.dumps({"provider": "northstar", "bundle": "standard", "max_price": "1400",
                       "target_price": "1300"})
    ratelimit.reset()
    with override_settings(UI_NEGOTIATE_PER_CLIENT=100, UI_NEGOTIATE_OVERALL=1):
        first = client.post("/api/ui/negotiate", body, content_type="application/json",
                            HTTP_X_FORWARDED_FOR="1.1.1.1")
        second = client.post("/api/ui/negotiate", body, content_type="application/json",
                             HTTP_X_FORWARDED_FOR="2.2.2.2")
    ratelimit.reset()
    assert (first.status_code, second.status_code) == (200, 429)
