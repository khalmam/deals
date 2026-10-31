"""Show the ledger catching an edit. The edit happens inside a transaction that is rolled
back, so your data is never changed. Usage: python manage.py tamper_demo [DEAL_ID] [--seq N]"""
from django.core.management.base import BaseCommand
from django.db import connection, transaction

from deals.management.commands.receipt import find_deal
from deals.models import LedgerEntry
from deals.services.ledger import verify_ledger


def describe(bad):
    return "intact" if bad is None else f"BROKEN at entry {bad + 1}"


class Command(BaseCommand):
    help = "Edit one ledger entry (then roll back) and show the chain detecting it."

    def add_arguments(self, parser):
        parser.add_argument("deal_id", nargs="?")
        parser.add_argument("--seq", type=int, default=2)

    def handle(self, *args, **opts):
        deal = find_deal(opts["deal_id"])
        self.stdout.write(f"before:             {describe(verify_ledger(deal))}")
        with transaction.atomic():
            if connection.vendor == "postgresql":
                self.stdout.write("(an admin switches off the database's edit protection...)")
                with connection.cursor() as c:
                    c.execute("SET CONSTRAINTS ALL IMMEDIATE")
                    c.execute("ALTER TABLE deals_ledgerentry DISABLE TRIGGER USER")
            row = LedgerEntry.objects.get(deal=deal, seq=opts["seq"])
            LedgerEntry.objects.filter(pk=row.pk).update(payload={"forged": "yes"})
            self.stdout.write(f"entry {opts['seq']} edited:    {describe(verify_ledger(deal))}")
            transaction.set_rollback(True)
        self.stdout.write(f"after rollback:     {describe(verify_ledger(deal))}")
