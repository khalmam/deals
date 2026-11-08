"""A thin client for the negotiation protocol, shared by buyer and provider agents.
`send(method, path, payload, token, headers)` returns (status, json). A retry reuses the
same Idempotency-Key, so a lost response can never create a second negotiation or message."""

RETRIES = 3


class ProtocolError(Exception):
    def __init__(self, status, body):
        super().__init__(f"{status} {body.get('code', '')}: {body.get('error', body)}")
        self.status, self.code = status, body.get("code", "")


class ProtocolClient:
    def __init__(self, send, token):
        self.send, self.token = send, token

    def _call(self, method, path, payload=None, key=None):
        headers = {"Idempotency-Key": key} if key else {}
        for attempt in range(RETRIES):
            try:
                status, body = self.send(method, path, payload, self.token, headers)
                break
            except (ConnectionError, TimeoutError):
                if attempt == RETRIES - 1:
                    raise
        if status not in (200, 201):
            raise ProtocolError(status, body)
        return body

    def me(self):
        """Who the server says this token belongs to."""
        return self._call("GET", "/api/agents/me")

    def provider(self, slug):
        return self._call("GET", f"/api/agents/{slug}")

    def open(self, provider, terms, key, expires_in=None):
        body = {"provider": provider, "terms": terms}
        if expires_in:
            body["expires_in"] = expires_in
        return self._call("POST", "/api/negotiations", body, key)

    def answer(self, negotiation_id, body, key):
        return self._call("POST", f"/api/negotiations/{negotiation_id}/messages", body, key)

    def get(self, negotiation_id, verify=False):
        return self._call("GET", f"/api/negotiations/{negotiation_id}" + ("?verify=1" if verify
                                                                          else ""))

    def inbox(self):
        return self._call("GET", "/api/negotiations")["results"]
