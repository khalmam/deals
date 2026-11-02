"""The whole product on real PayPal sandbox: negotiate, hold, deliver, capture, pay the
sub-contractor. A human approves the hold on PayPal's page. Usage:
python manage.py run_deal --sub-email SANDBOX_SUB_EMAIL [--client EMAIL] [--ceiling 1650]"""
import time

from django.conf import settings
from django.core.management.base import BaseCommand

from agents.client_sim import Persona, ScriptedClient
from agents.freelancer import FreelancerAgent
from agents.llm import ClaudeLLM, NoModel
from agents.spend_guard import MemoryStore, SpendGuard
from deals.domain.mandate import Mandate
from deals.domain.money import Money
from deals.management.paypal_factory import payments_from_settings
from deals.services.confirm_hold import confirm_hold
from deals.services.delivery_capture_void import capture, confirm_delivery
from deals.services.ledger import verify_ledger
from deals.services.mandate import set_mandate
from deals.services.negotiate import negotiate
from deals.services.open_deal import open_deal
from deals.services.open_hold import open_hold
from deals.services.refresh_payouts import refresh_payouts
from deals.services.send_payouts import send_payouts
from engine.demo_card import demo_card


class Command(BaseCommand):
    help = "Negotiate, hold, capture and pay out one deal on PayPal sandbox."

    def add_arguments(self, parser):
        parser.add_argument("--sub-email", required=True, help="sandbox account of the illustrator")
        parser.add_argument("--client", default="khal2@personal.example.com")
        parser.add_argument("--target", default="1200")
        parser.add_argument("--ceiling", default="1650")
        parser.add_argument("--wait", type=int, default=12, help="payout checks, 5 seconds apart")

    def handle(self, *args, **opts):
        mandate = Mandate(True, {"illustrator": opts["sub_email"]})  # fails fast on a bad email
        payments = payments_from_settings()
        key = settings.ANTHROPIC_API_KEY
        llm = ClaudeLLM(key, settings.ANTHROPIC_MODEL) if key else NoModel()
        persona = Persona("demo client", Money.of(opts["target"]), Money.of(opts["ceiling"]),
                          seed=1)
        deal = open_deal("Brand identity", opts["client"])
        agent = FreelancerAgent(llm, SpendGuard(MemoryStore()))
        out = negotiate(deal, demo_card(), "standard", agent, ScriptedClient(persona))
        self.stdout.write(f"negotiation: {out.status}" + (f" at {out.price}" if out.price else ""))
        if out.status != "AGREED":
            return
        set_mandate(deal, mandate)
        open_hold(deal, payments, "https://example.com/ok", "https://example.com/no")
        self.stdout.write(f"\nAPPROVE AS THE BUYER:\n{deal.approve_url}")
        input("Press Enter after approving... ")
        confirm_hold(deal, payments)
        confirm_delivery(deal)
        capture(deal, payments)
        send_payouts(deal, payments, actor="agent")
        self.stdout.write("payout sent; waiting for PayPal...")
        for _ in range(opts["wait"]):
            refresh_payouts(deal, payments)
            if deal.state == "PAID_OUT":
                break
            time.sleep(5)
        bad = verify_ledger(deal)
        self.stdout.write(f"\ndeal: {deal.pk}\nstate: {deal.state}")
        for e in deal.ledger.order_by("seq"):
            self.stdout.write(f"  {e.seq:>2} {e.kind:<22} {e.hash[:12]}")
        self.stdout.write("ledger: " + ("intact" if bad is None else f"BROKEN at entry {bad}"))
