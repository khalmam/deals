"""Print the generated state-machine reference, or refresh it in a doc.
Usage: python manage.py machines [--write docs/STATE_MACHINES.md]"""
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from deals.domain.machines import END, START, reference


def splice(text, block):
    """`text` with the generated block between the markers replaced by `block`."""
    if START not in text or END not in text:
        raise CommandError(f"the file needs {START} and {END} markers")
    head, rest = text.split(START, 1)
    return f"{head}{START}\n{block}\n{END}{rest.split(END, 1)[1]}"


class Command(BaseCommand):
    help = "Print the state-machine reference generated from the domain tables."

    def add_arguments(self, parser):
        parser.add_argument("--write", metavar="FILE",
                            help="replace the generated block in this file")

    def handle(self, *args, **opts):
        if not opts["write"]:
            self.stdout.write(reference())
            return
        path = Path(opts["write"])
        path.write_text(splice(path.read_text(), reference()))
        self.stdout.write(f"updated {path}")
