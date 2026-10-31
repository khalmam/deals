import json

import httpx
import pytest

from paypal.client import PayPalClient, PayPalConfig, PayPalError, request_key

CFG = PayPalConfig("id", "secret")


def make(handler):
    return PayPalClient(CFG, transport=httpx.MockTransport(handler))


def token_ok(request):
    return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})


def test_token_is_cached_between_requests():
    calls = {"token": 0}

    def handler(request):
        if request.url.path == "/v1/oauth2/token":
            calls["token"] += 1
            return token_ok(request)
        return httpx.Response(200, json={"ok": True})

    c = make(handler)
    c.request("GET", "/a")
    c.request("GET", "/b")
    assert calls["token"] == 1


def test_post_without_body_still_sends_json():
    seen = {}

    def handler(request):
        if request.url.path == "/v1/oauth2/token":
            return token_ok(request)
        seen["body"] = request.content
        seen["type"] = request.headers["content-type"]
        seen["rid"] = request.headers["paypal-request-id"]
        return httpx.Response(200, json={})

    make(handler).request("POST", "/x", request_id="abc")
    assert json.loads(seen["body"]) == {}
    assert seen["type"] == "application/json"
    assert seen["rid"] == "abc"


def test_error_is_typed_with_issues():
    def handler(request):
        if request.url.path == "/v1/oauth2/token":
            return token_ok(request)
        return httpx.Response(422, json={"name": "UNPROCESSABLE_ENTITY", "message": "no",
                                         "details": [{"issue": "REAUTHORIZATION_TOO_SOON"}]})

    with pytest.raises(PayPalError) as err:
        make(handler).request("POST", "/x")
    assert err.value.status == 422
    assert "REAUTHORIZATION_TOO_SOON" in err.value.issues


def test_expired_token_is_refreshed_once_on_401():
    state = {"api": 0}

    def handler(request):
        if request.url.path == "/v1/oauth2/token":
            return token_ok(request)
        state["api"] += 1
        return httpx.Response(401 if state["api"] == 1 else 200, json={})

    make(handler).request("GET", "/x")
    assert state["api"] == 2


def test_request_key_is_stable_and_short():
    assert request_key("deal", "capture", 1) == request_key("deal", "capture", 1)
    assert request_key("deal", "capture", 1) != request_key("deal", "capture", 2)
    assert len(request_key("a" * 500)) == 64
