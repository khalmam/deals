"""The HTTP transport the demo commands use to reach a Deals server."""
import stat
import sys
from pathlib import Path

import httpx


def read_secret(path):
    """Read a token or number from a file, warning if other users can read it."""
    file = Path(path).expanduser()
    if file.stat().st_mode & (stat.S_IRWXG | stat.S_IRWXO):
        print(f"warning: {file} is readable by other users; run chmod 600 on it", file=sys.stderr)
    return file.read_text().strip()


def make_send(base_url, timeout=30):
    http = httpx.Client(base_url=base_url, timeout=timeout)

    def send(method, path, payload, token, headers=None):
        try:
            r = http.request(method, path, headers={"Authorization": f"Bearer {token}",
                                                    **(headers or {})},
                             json=payload if method != "GET" else None)
        except httpx.TransportError as exc:
            raise ConnectionError(str(exc)) from exc
        try:
            return r.status_code, r.json()
        except ValueError:
            return r.status_code, {"error": r.text[:200]}
    return send
