from io import StringIO

import pytest
from django.core.management import call_command

from tests.fakes import FakePayments

pytestmark = pytest.mark.django_db


def test_run_deal_goes_from_brief_to_paid_out(monkeypatch):
    from deals.management.commands import run_deal
    pay = FakePayments()
    monkeypatch.setattr(run_deal, "payments_from_settings", lambda: pay)
    monkeypatch.setattr("builtins.input", lambda _: "")
    out = StringIO()
    call_command("run_deal", "--sub-email", "ill@x.com", stdout=out)
    text = out.getvalue()
    assert "negotiation: AGREED at 1620.00 USD" in text and "state: PAID_OUT" in text
    assert "ledger: intact" in text and text.count("AGENT_ACTION") == 3
    assert pay.payouts[0][0].receiver_email == "ill@x.com"
    assert str(pay.payouts[0][0].amount) == "225.00 USD"


def test_run_deal_stops_when_the_client_walks_away(monkeypatch):
    from deals.management.commands import run_deal
    pay = FakePayments()
    monkeypatch.setattr(run_deal, "payments_from_settings", lambda: pay)
    out = StringIO()
    call_command("run_deal", "--sub-email", "ill@x.com", "--ceiling", "1000",
                 "--target", "800", stdout=out)
    assert "WALKED_AWAY" in out.getvalue() and not pay.calls


def test_run_deal_refuses_a_placeholder_email_before_anything_happens(monkeypatch):
    from deals.domain.mandate import MandateViolation
    from deals.management.commands import run_deal
    from deals.models import Deal
    pay = FakePayments()
    monkeypatch.setattr(run_deal, "payments_from_settings", lambda: pay)
    with pytest.raises(MandateViolation):
        call_command("run_deal", "--sub-email", "YOUR_ILLUSTRATOR_SANDBOX_EMAIL")
    assert not pay.calls and Deal.objects.count() == 0
