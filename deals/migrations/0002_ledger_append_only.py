"""On Postgres, block UPDATE, DELETE and TRUNCATE on ledger entries at the database level.
Other databases (the SQLite used by fast unit tests) skip this."""
from django.db import migrations

CREATE = """
CREATE FUNCTION deals_ledger_block_change() RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION 'ledger entries are append-only';
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER deals_ledger_no_row_change BEFORE UPDATE OR DELETE ON deals_ledgerentry
  FOR EACH ROW EXECUTE FUNCTION deals_ledger_block_change();
CREATE TRIGGER deals_ledger_no_truncate BEFORE TRUNCATE ON deals_ledgerentry
  FOR EACH STATEMENT EXECUTE FUNCTION deals_ledger_block_change();
"""

DROP = """
DROP TRIGGER IF EXISTS deals_ledger_no_truncate ON deals_ledgerentry;
DROP TRIGGER IF EXISTS deals_ledger_no_row_change ON deals_ledgerentry;
DROP FUNCTION IF EXISTS deals_ledger_block_change();
"""


def forwards(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(CREATE)


def backwards(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(DROP)


class Migration(migrations.Migration):
    dependencies = [("deals", "0001_initial")]
    operations = [migrations.RunPython(forwards, backwards)]
