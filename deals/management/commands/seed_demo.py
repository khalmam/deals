"""Create the demo provider if it is missing. Safe to run on every start."""
from django.conf import settings
from django.core.management.base import BaseCommand

from deals.services.seed_demo import seed_hosted_provider, seed_more_providers


class Command(BaseCommand):
    help = "Create the hosted demo provider (Northstar Hosted) if it does not exist."

    def handle(self, *args, **options):
        outcome = seed_hosted_provider(settings.DEMO_SUB_EMAIL)
        note = " (set DEMO_SUB_EMAIL to create it)" if outcome == "skipped" else ""
        self.stdout.write(f"demo provider: {outcome}{note}")
        for name, result in seed_more_providers(settings.DEMO_SUB_EMAIL).items():
            self.stdout.write(f"demo provider {name}: {result}")
