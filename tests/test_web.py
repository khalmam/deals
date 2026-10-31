from django.test import Client


def test_health_endpoint(settings):
    r = Client().get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "up"}
