"""Provision an agent and print its one-time API credential."""
import json

from django.core.management.base import BaseCommand, CommandError

from deals.services.agent_registry import issue_credential, register_agent

DEFAULT_PROVIDER_MANDATE = {"allow_hold": True, "allow_capture": True, "allow_void": True}
AGENT_SCOPES = ["directory:read", "deals:negotiate"]


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
        parser.add_argument("--mandate", default="", help="JSON: provider payout rules, or "
                            'buyer budget such as {"max_deal": "1500", "currency": "USD"}')
        parser.add_argument("--hosted", action="store_true", help="Deals runs this provider")
        parser.add_argument("--scopes", default="", help="comma-separated; defaults by type")

    def handle(self, *args, **options):
        try:
            json.loads(options["mandate"] or "{}")
            capabilities = json.loads(options["capabilities"])
            services = json.loads(options["services"])
            if not isinstance(capabilities, list) or not isinstance(services, list):
                raise ValueError("Capabilities and services must be JSON arrays.")
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        mandate = json.loads(options["mandate"]) if options["mandate"] else (
            DEFAULT_PROVIDER_MANDATE if options["type"] == "PROVIDER" else {})
        scopes = [s.strip() for s in options["scopes"].split(",") if s.strip()] or (
            AGENT_SCOPES)
        try:
            agent = register_agent(
                name=options["name"], agent_type=options["type"],
                owner_name=options["owner_name"], owner_email=options["owner_email"],
                description=options["description"], capabilities=capabilities,
                services=services, mandate=mandate, is_public=not options["private"],
                hosted=options["hosted"],
            )
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        _, token = issue_credential(agent, scopes)
        self.stdout.write(self.style.SUCCESS(f"Agent created: {agent.slug} ({agent.pk})"))
        self.stdout.write(f"API token (shown once): {token}")
