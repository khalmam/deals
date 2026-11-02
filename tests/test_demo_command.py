from io import StringIO

import pytest
from django.core.management import call_command

pytestmark = pytest.mark.django_db


def test_negotiate_demo_runs_offline_and_agrees():
    out = StringIO()
    call_command("negotiate_demo", stdout=out)
    text = out.getvalue()
    assert "rules engine only" in text and "result: AGREED at 1620.00 USD" in text


def test_negotiate_demo_walks_away_from_a_client_who_cannot_afford_it():
    out = StringIO()
    call_command("negotiate_demo", "--ceiling", "1000", "--target", "800",
                 "--patience", "3", stdout=out)
    assert "result: WALKED_AWAY" in out.getvalue()
