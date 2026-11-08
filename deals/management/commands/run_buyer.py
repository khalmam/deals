"""Run a buyer agent against a Deals server over HTTP, using only its bearer token."""
import json
from pathlib import Path

import httpx
from django.core.management.base import BaseCommand, CommandError

from agents.buyer_client import BuyerAgent, BuyerError


class Command(BaseCommand):
    help = "Negotiate a deal as a registered buyer agent through the public HTTP API."

    def add_arguments(self, parser):
        parser.add_argument("--base-url", default="http://localhost:8000")
        parser.add_argument("--token-file", required=True, help="file holding the dl_ token")
        parser.add_argument("--provider", required=True, help="provider slug from /api/agents")
        parser.add_argument("--bundle", default="standard")
        parser.add_argument("--budget", required=True, help="the buyer's ceiling, whole units")
        parser.add_argument("--currency", default="USD")

    def handle(self, *args, **options):
        token = Path(options["token_file"]).read_text().strip()
        http = httpx.Client(base_url=options["base_url"], timeout=60)

        def send(method, path, payload, token):
            r = http.request(method, path, headers={"Authorization": f"Bearer {token}"},
                             content=json.dumps(payload) if payload is not None else None)
            return r.status_code, r.json()

        agent = BuyerAgent(send, token, options["budget"], options["currency"])
        try:
            result = agent.negotiate(options["provider"], options["bundle"])
        except BuyerError as exc:
            raise CommandError(str(exc)) from exc
        for line in result["log"]:
            self.stdout.write(f"  {line}")
        self.stdout.write(self.style.SUCCESS(
            f"{result['status']} at {result['price']} {result['currency']}"))
        if result["approve_url"]:
            self.stdout.write(f"Owner approves the hold here: {result['approve_url']}")
