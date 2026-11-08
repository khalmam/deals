from django.test import override_settings

from deals.management import live_factory


def test_the_live_setup_starts_without_a_demo_sub_email(monkeypatch):
    monkeypatch.setattr(live_factory, "llm_from_settings", lambda: (object(), "test"))
    monkeypatch.setattr(live_factory, "payments_from_settings", lambda: None)
    live_factory.live_deps.cache_clear()
    try:
        with override_settings(DEMO_SUB_EMAIL=""):
            assert live_factory.live_deps().mandate.approved_subs == {}
        live_factory.live_deps.cache_clear()
        with override_settings(DEMO_SUB_EMAIL="sub@example.com"):
            assert live_factory.live_deps().mandate.approved_subs == {
                "illustrator": "sub@example.com"}
    finally:
        live_factory.live_deps.cache_clear()
