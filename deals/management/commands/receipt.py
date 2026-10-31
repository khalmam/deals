"""Print a deal's sealed receipt. Usage: python manage.py receipt [DEAL_ID] [--html FILE]
[--check-paypal]. With no id it uses the newest deal."""
from django.core.management.base import BaseCommand, CommandError

from deals.management.paypal_factory import payments_from_settings
from deals.models import Deal
from deals.services.seal import anchor_ok, build_receipt
from render.sealed_receipt import receipt_html, receipt_text


def find_deal(deal_id):
    try:
        return Deal.objects.get(pk=deal_id) if deal_id else Deal.objects.latest("created_at")
    except (Deal.DoesNotExist, ValueError) as exc:
        raise CommandError("no such deal") from exc


class Command(BaseCommand):
    help = "Print the sealed receipt for a deal."

    def add_arguments(self, parser):
        parser.add_argument("deal_id", nargs="?")
        parser.add_argument("--html", help="also write the receipt as a web page to this file")
        parser.add_argument("--check-paypal", action="store_true",
                            help="ask PayPal whether its stored hash matches ours")

    def handle(self, *args, **opts):
        deal = find_deal(opts["deal_id"])
        anchor = anchor_ok(deal, payments_from_settings()) if opts["check_paypal"] else None
        data = build_receipt(deal, anchor)
        self.stdout.write(receipt_text(data))
        if opts["html"]:
            with open(opts["html"], "w") as fh:
                fh.write(receipt_html(data))
            self.stdout.write(f"\nwrote {opts['html']}")
