"""An independent provider agent: it polls Deals over HTTP and keeps its floor to itself."""
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError

from agents.negotiating_provider import ExternalProvider, ProviderPolicy
from agents.protocol_client import ProtocolClient
from deals.management.demo_runners import own_slug, run_provider
from deals.management.protocol_http import make_send, read_secret


class Command(BaseCommand):
    help = "Run an independent provider agent against a Deals server."

    def add_arguments(self, parser):
        parser.add_argument("--base-url", default="http://localhost:8000")
        parser.add_argument("--token-file", required=True)
        parser.add_argument("--slug", default="", help="optional; checked against the token")
        parser.add_argument("--list-price", required=True)
        parser.add_argument("--floor-file", required=True, help="file holding the private floor")
        parser.add_argument("--currency", default="USD")
        parser.add_argument("--interval", type=float, default=2)
        parser.add_argument("--once", action="store_true", help="answer what is waiting, then stop")

    def handle(self, *args, **options):
        policy = ProviderPolicy(Decimal(options["list_price"]),
                                Decimal(read_secret(options["floor_file"])), options["currency"])
        client = ProtocolClient(make_send(options["base_url"]), read_secret(options["token_file"]))
        try:
            slug = own_slug(client, options["slug"])
            run_provider(ExternalProvider(client, slug, policy), self.stdout.write,
                         options["interval"], options["once"])
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        except KeyboardInterrupt:
            self.stdout.write("stopped")
