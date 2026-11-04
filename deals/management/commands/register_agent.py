"""Provision an agent and print its one-time API credential."""
import json

from django.core.management.base import BaseCommand, CommandError

from deals.services.agent_registry import issue_credential, register_agent


class Command(BaseCommand):
    help = "Register a Deals agent and issue its one-time bearer credential."

    def add_arguments(self, parser):
        parser.add_argument("--name", required=True)
        parser.add_argument("--type", required=True, choices=["PROVIDER", "BUYER"])
        parser.add_argument("--owner-name", required=True)
        parser.add_argument("--owner-email", required=True)
        parser.add_argument("--description", default="")
        parser.add_argument("--capabilities", default="[]")
        parser.add_argument("--services", default="[]")
        parser.add_argument("--private", action="store_true")

    def handle(self, *args, **options):
        try:
            capabilities = json.loads(options["capabilities"])
            services = json.loads(options["services"])
            if not isinstance(capabilities, list) or not isinstance(services, list):
                raise ValueError("Capabilities and services must be JSON arrays.")
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        agent = register_agent(
            name=options["name"], agent_type=options["type"],
            owner_name=options["owner_name"], owner_email=options["owner_email"],
            description=options["description"], capabilities=capabilities,
            services=services, is_public=not options["private"],
        )
        _, token = issue_credential(agent)
        self.stdout.write(self.style.SUCCESS(f"Agent created: {agent.slug} ({agent.pk})"))
        self.stdout.write(f"API token (shown once): {token}")
