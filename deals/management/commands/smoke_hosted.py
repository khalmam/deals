"""Check a deployed Deals server the way a visitor and an agent would."""
import httpx
from django.core.management.base import BaseCommand, CommandError

from agents.negotiating_buyer import BuyerPolicy, ProcurementAgent
from agents.protocol_client import ProtocolClient
from deals.management.demo_runners import own_slug, run_procurement
from deals.management.protocol_http import make_send, read_secret


class Command(BaseCommand):
    help = "Smoke-test a Deals deployment. Add --token-file to also run a negotiation."

    def add_arguments(self, parser):
        parser.add_argument("--base-url", required=True)
        parser.add_argument("--token-file")
        parser.add_argument("--slug", default="")
        parser.add_argument("--provider", default="")
        parser.add_argument("--bundle", default="standard")
        parser.add_argument("--max-price", default="1400")

    def _check(self, name, ok, failures):
        self.stdout.write(f"{'PASS' if ok else 'FAIL'}  {name}")
        if not ok:
            failures.append(name)

    def handle(self, *args, **options):
        base, failures = options["base_url"].rstrip("/"), []
        for path in ("/", "/agents/", "/api/agents"):
            self._check(f"GET {path} answers 200", httpx.get(base + path, timeout=30,
                        follow_redirects=True).status_code == 200, failures)
        listing = httpx.get(base + "/api/agents?type=PROVIDER", timeout=30).text.lower()
        self._check("the public directory shows no floor or payout split",
                    not any(w in listing for w in ("floor", "sub_id", "sub_pct")), failures)
        if options["token_file"]:
            price = options["max_price"]
            from decimal import Decimal
            policy = BuyerPolicy(Decimal(price), Decimal(price) * Decimal("0.93"), 30, 7,
                                 Decimal(5))
            client = ProtocolClient(make_send(base), read_secret(options["token_file"]))
            agent = ProcurementAgent(client, own_slug(client, options["slug"]), policy)
            final = run_procurement(agent, options["provider"], options["bundle"],
                                    self.stdout.write, interval=1, limit=30)
            self._check("the negotiation reached AGREED", final["status"] == "AGREED", failures)
            self._check("the history verifies", final["verification"]["intact"], failures)
        if failures:
            raise CommandError(f"{len(failures)} check(s) failed")
        self.stdout.write(self.style.SUCCESS("all checks passed"))
