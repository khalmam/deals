"""Run one real sandbox deal end to end. A human approves the hold on PayPal's page.
Usage: python manage.py run_flow [--void]"""
from django.core.management.base import BaseCommand

from deals.management.paypal_factory import payments_from_settings
from deals.services.confirm_hold import confirm_hold
from deals.services.delivery_capture_void import capture, confirm_delivery, void
from deals.services.ledger import verify_ledger
from deals.services.open_deal import agree_terms, open_deal
from deals.services.open_hold import open_hold

TERMS = {"bundle": "starter", "total": "25.00", "currency": "USD",
         "line_items": [{"name": "Logo design", "amount": "25.00"}]}


class Command(BaseCommand):
    help = "Open a deal, hold the money on PayPal sandbox, then capture it (or void with --void)."

    def add_arguments(self, parser):
        parser.add_argument("--void", action="store_true", help="release the hold instead")
        parser.add_argument("--client", default="khal2@personal.example.com")

    def handle(self, *args, **opts):
        payments = payments_from_settings()
        deal = open_deal("Logo design", opts["client"])
        agree_terms(deal, TERMS)
        open_hold(deal, payments, "https://example.com/ok", "https://example.com/no")
        self.stdout.write(f"\nterms hash: {deal.terms_hash}")
        self.stdout.write(f"APPROVE AS THE BUYER:\n{deal.approve_url}")
        input("Press Enter after approving... ")
        confirm_hold(deal, payments)
        self.stdout.write(f"hold active until {deal.authorization_expires}")
        if opts["void"]:
            void(deal, payments)
        else:
            confirm_delivery(deal)
            capture(deal, payments)
        bad = verify_ledger(deal)
        self.stdout.write(f"\ndeal: {deal.pk}\nstate: {deal.state}")
        for e in deal.ledger.order_by("seq"):
            self.stdout.write(f"  {e.seq:>2} {e.kind:<20} {e.hash[:12]}")
        self.stdout.write("ledger: " + ("intact" if bad is None else f"BROKEN at entry {bad}"))
