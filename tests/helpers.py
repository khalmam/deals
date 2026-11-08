from django.db import connection

from deals.models import LedgerEntry


def forge_entry(deal, seq, payload=None):
    """Edit history the way an admin with database rights could: switch the trigger off first."""
    if connection.vendor == "postgresql":
        with connection.cursor() as c:  # undone when the test's transaction rolls back
            c.execute("SET CONSTRAINTS ALL IMMEDIATE")
            c.execute("ALTER TABLE deals_ledgerentry DISABLE TRIGGER USER")
    LedgerEntry.objects.filter(deal=deal, seq=seq).update(
        payload=payload or {"x": "forged"})


def as_admin(*tables):
    """Switch the append-only triggers off for these tables, as a database admin could.
    Undone when the test's transaction rolls back. A no-op on SQLite, which has none."""
    if connection.vendor == "postgresql":
        with connection.cursor() as c:
            c.execute("SET CONSTRAINTS ALL IMMEDIATE")
            for table in tables:
                c.execute(f"ALTER TABLE {table} DISABLE TRIGGER USER")
