from django.db import connection

from deals.models import LedgerEntry


def forge_entry(deal, seq):
    """Edit history the way an admin with database rights could: switch the trigger off first."""
    if connection.vendor == "postgresql":
        with connection.cursor() as c:  # undone when the test's transaction rolls back
            c.execute("SET CONSTRAINTS ALL IMMEDIATE")
            c.execute("ALTER TABLE deals_ledgerentry DISABLE TRIGGER USER")
    LedgerEntry.objects.filter(deal=deal, seq=seq).update(payload={"x": "forged"})
