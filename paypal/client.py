"""Thin PayPal REST client: token cache, JSON bodies, stable idempotency keys, typed errors."""
import hashlib
import time
import uuid
from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class PayPalConfig:
    client_id: str
    client_secret: str
    base_url: str = "https://api-m.sandbox.paypal.com"
    webhook_id: str = ""


class PayPalError(Exception):
    def __init__(self, status, name="", message="", issues=(), debug_id=""):
        self.status, self.name, self.message = status, name, message
        self.issues, self.debug_id = tuple(issues), debug_id
        super().__init__(f"PayPal {status} {name}: {message} {list(self.issues)}")


def request_key(*parts):
    """Same deal + same step => same key, so a retry can never double-charge."""
    return hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()


def _error(resp):
    try:
        d = resp.json()
    except ValueError:
        d = {}
    issues = [x.get("issue", "") for x in d.get("details", []) if isinstance(x, dict)]
    return PayPalError(resp.status_code, d.get("name", ""), d.get("message", resp.text[:200]),
                       issues, d.get("debug_id", ""))


class PayPalClient:
    def __init__(self, config, transport=None, clock=time.monotonic):
        self._cfg = config
        self._clock = clock
        self._http = httpx.Client(base_url=config.base_url, timeout=30, transport=transport)
        self._token = None
        self._expires = 0.0

    def _access_token(self):
        if self._token and self._clock() < self._expires - 60:
            return self._token
        r = self._http.post("/v1/oauth2/token", data={"grant_type": "client_credentials"},
                            auth=(self._cfg.client_id, self._cfg.client_secret))
        if r.status_code != 200:
            raise _error(r)
        d = r.json()
        self._token = d["access_token"]
        self._expires = self._clock() + int(d.get("expires_in", 300))
        return self._token

    def request(self, method, path, body=None, request_id=None, _retry=True):
        headers = {"Authorization": f"Bearer {self._access_token()}"}
        payload = body
        if method == "POST":
            headers["PayPal-Request-Id"] = request_id or str(uuid.uuid4())
            if payload is None:
                payload = {}  # PayPal answers 415 to a POST with no JSON body
        r = self._http.request(method, path, headers=headers, json=payload)
        if r.status_code == 401 and _retry:
            self._token = None
            return self.request(method, path, body, request_id, _retry=False)
        if r.status_code >= 400:
            raise _error(r)
        return r.json() if r.content else {}
