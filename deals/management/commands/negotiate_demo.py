"""Negotiate a deal between the freelancer's agent and a simulated client, then show the
transcript. Uses Claude if ANTHROPIC_API_KEY is set, otherwise the rules engine alone.
No PayPal calls. Usage: python manage.py negotiate_demo [--ceiling 1650] [--target 1200]"""
from django.conf import settings
from django.core.management.base import BaseCommand

from agents.client_sim import Persona, ScriptedClient
from agents.freelancer import FreelancerAgent
from agents.llm import ClaudeLLM, NoModel
from agents.spend_guard import MemoryStore, SpendGuard
from deals.domain.money import Money
from deals.services.negotiate import negotiate
from deals.services.open_deal import open_deal
from engine.demo_card import demo_card


class Command(BaseCommand):
    help = "Run one negotiation and print the transcript."

    def add_arguments(self, parser):
        parser.add_argument("--bundle", default="standard")
        parser.add_argument("--target", default="1200")
        parser.add_argument("--ceiling", default="1650")
        parser.add_argument("--patience", type=int, default=8)
        parser.add_argument("--seed", type=int, default=1)

    def handle(self, *args, **opts):
        key = settings.ANTHROPIC_API_KEY
        llm = ClaudeLLM(key, settings.ANTHROPIC_MODEL) if key else NoModel()
        who = "Claude" if key else "rules engine only (no ANTHROPIC_API_KEY)"
        persona = Persona("demo client", Money.of(opts["target"]), Money.of(opts["ceiling"]),
                          patience=opts["patience"], seed=opts["seed"])
        deal = open_deal("Brand identity", "khal2@personal.example.com")
        agent = FreelancerAgent(llm, SpendGuard(MemoryStore()))
        out = negotiate(deal, demo_card(), opts["bundle"], agent, ScriptedClient(persona))
        self.stdout.write(f"freelancer agent: {who}\n")
        for e in deal.ledger.filter(kind__in=["OFFER_MADE", "COUNTER_MADE"]).order_by("seq"):
            p = e.payload
            price = p.get("price", "walks away")
            tag = f" [{p['source']}]" if "source" in p else ""
            self.stdout.write(f"{p['by']:>10}: {price:>8}{tag}  {p['message']}")
        self.stdout.write(f"\nresult: {out.status}" + (f" at {out.price}" if out.price else ""))
        if out.price:
            t = deal.terms
            self.stdout.write(f"you keep {t['freelancer_net']}; sub-contractors: {t['payouts']}")
            self.stdout.write(f"terms hash {deal.terms_hash[:16]}...  deal {deal.pk}")
