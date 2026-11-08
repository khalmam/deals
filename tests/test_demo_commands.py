import os
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.core.management import CommandError, call_command

from agents.negotiating_buyer import BuyerPolicy, ProcurementAgent
from agents.negotiating_provider import ExternalProvider, ProviderPolicy
from deals.management.demo_runners import own_slug, run_procurement, run_provider
from deals.management.protocol_http import read_secret
from tests.neg_helpers import LOCAL_FLOOR

POLICY = BuyerPolicy(Decimal(1400), Decimal(1300), 30, 7, Decimal(5))


def procurement(wire, parties):
    return ProcurementAgent(wire.client_for(parties["buyer_token"]), "amanah-procurement", POLICY)


def test_the_buyer_runner_prints_the_negotiation_and_verifies_it(wire, parties):
    lines = []
    final = run_procurement(procurement(wire, parties), "northstar", "standard", lines.append,
                            sleep=lambda s: None)
    assert final["status"] == "AGREED" and final["verification"]["intact"]
    assert lines[0].startswith("amanah-procurement opens a negotiation")
    assert any("PROPOSE" in line for line in lines) and any("ACCEPT" in line for line in lines)
    assert len(lines) == 1 + len(final["messages"])  # each message shown exactly once


def test_two_independent_agents_agree_through_the_server(wire, parties):
    """The provider runs on its own clock: it answers whenever the buyer waits."""
    provider = ExternalProvider(wire.client_for(parties["outside_token"]), "freelance-ext",
                                ProviderPolicy(Decimal(1800), Decimal(LOCAL_FLOOR)))
    theirs, mine = [], []
    final = run_procurement(procurement(wire, parties), "freelance-ext", "standard", mine.append,
                            sleep=lambda s: run_provider(provider, theirs.append, once=True))
    assert final["status"] == "AGREED" and final["verification"]["intact"]
    assert any(line.startswith("  answered") for line in theirs)
    assert LOCAL_FLOOR not in "".join(wire.seen + mine + theirs)


def test_the_provider_loop_can_be_bounded(wire, parties):
    provider = ExternalProvider(wire.client_for(parties["outside_token"]), "freelance-ext",
                                ProviderPolicy(Decimal(1800), Decimal(LOCAL_FLOOR)))
    out, naps = [], []
    run_provider(provider, out.append, limit=3, sleep=naps.append)
    assert len(naps) == 3 and out[0].endswith("its floor stays on this machine")


def test_secret_files_that_others_can_read_get_a_warning(tmp_path, capsys):
    secret = tmp_path / "token"
    secret.write_text("dl_secret\n")
    os.chmod(secret, 0o644)
    assert read_secret(secret) == "dl_secret"
    assert "chmod 600" in capsys.readouterr().err
    os.chmod(secret, 0o600)
    read_secret(secret)
    assert capsys.readouterr().err == ""


def serve_through(client, monkeypatch, leak=""):
    """Route the smoke command's HTTP calls to the Django test client. No live server: those
    need a transactional database, whose cleanup TRUNCATEs the append-only tables."""
    def get(url, **kwargs):
        reply = client.get(url.removeprefix("http://testserver"), follow=True)
        return SimpleNamespace(status_code=reply.status_code,
                               text=reply.content.decode() + (leak if "/api/agents" in url else ""))
    monkeypatch.setattr("deals.management.commands.smoke_hosted.httpx.get", get)


def test_smoke_command_passes_a_healthy_server(client, db, parties, monkeypatch, capsys):
    serve_through(client, monkeypatch)
    call_command("smoke_hosted", base_url="http://testserver")
    assert "all checks passed" in capsys.readouterr().out


def test_smoke_command_fails_if_the_directory_leaks_a_floor(client, db, monkeypatch, capsys):
    serve_through(client, monkeypatch, leak='{"floor": "1000"}')
    with pytest.raises(CommandError, match="1 check"):
        call_command("smoke_hosted", base_url="http://testserver")
    assert "FAIL  the public directory" in capsys.readouterr().out


def test_the_server_tells_an_agent_who_it_is(wire, parties):
    client = wire.client_for(parties["buyer_token"])
    assert own_slug(client) == parties["buyer"].slug
    assert own_slug(client, parties["buyer"].slug) == parties["buyer"].slug
    with pytest.raises(ValueError, match=f"belongs to {parties['buyer'].slug}"):
        own_slug(client, "amanah-procurement-typo")


def test_an_agent_with_the_wrong_slug_gets_a_clear_error_not_an_index_error(wire, parties):
    real = procurement(wire, parties)
    real.start("freelance-ext", "standard")
    impostor = ProcurementAgent(wire.client_for(parties["buyer_token"]), "someone-else", POLICY)
    impostor.negotiation_id = real.negotiation_id
    with pytest.raises(RuntimeError, match="not opened by someone-else"):
        impostor.step()
