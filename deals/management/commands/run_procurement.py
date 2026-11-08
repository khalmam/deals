"""A buyer agent that negotiates with a provider through the structured protocol."""
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError

from agents.negotiating_buyer import BuyerPolicy, ProcurementAgent
from agents.protocol_client import ProtocolClient, ProtocolError
from deals.management.demo_runners import own_slug, run_procurement
from deals.management.protocol_http import make_send, read_secret


class Command(BaseCommand):
    help = "Negotiate a deal as a buyer agent, within the limits you set."

    def add_arguments(self, parser):
        parser.add_argument("--base-url", default="http://localhost:8000")
        parser.add_argument("--token-file", required=True)
        parser.add_argument("--slug", default="", help="optional; checked against the token")
        parser.add_argument("--provider", required=True)
        parser.add_argument("--bundle", default="standard")
        parser.add_argument("--max-price", required=True, help="the ceiling; never exceeded")
        parser.add_argument("--target-price", required=True, help="accepted at once if reached")
        parser.add_argument("--max-delivery-days", type=int, default=30)
        parser.add_argument("--min-net-days", type=int, default=7)
        parser.add_argument("--max-late-fee-pct", default="5")
        parser.add_argument("--currency", default="USD")
        parser.add_argument("--interval", type=float, default=2)

    def handle(self, *args, **options):
        policy = BuyerPolicy(Decimal(options["max_price"]), Decimal(options["target_price"]),
                             options["max_delivery_days"], options["min_net_days"],
                             Decimal(options["max_late_fee_pct"]), options["currency"])
        client = ProtocolClient(make_send(options["base_url"]), read_secret(options["token_file"]))
        try:
            agent = ProcurementAgent(client, own_slug(client, options["slug"]), policy)
            final = run_procurement(agent, options["provider"], options["bundle"],
                                    self.stdout.write, options["interval"])
        except (ProtocolError, ValueError) as exc:
            raise CommandError(str(exc)) from exc
        price = final["standing_terms"]["price"]
        self.stdout.write(self.style.SUCCESS(
            f"{final['status']} at {price['amount']} {price['currency']}; history intact: "
            f"{final['verification']['intact']}"))
        if final["status"] == "OPEN":
            raise CommandError("the other side has not answered yet; run it again to resume")
