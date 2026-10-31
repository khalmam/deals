import pytest

from config.env import ConfigError, env, env_list, parse_database_url


def test_required_missing_raises(monkeypatch):
    monkeypatch.delenv("NOPE_X", raising=False)
    with pytest.raises(ConfigError):
        env("NOPE_X", required=True)


def test_env_list_splits_and_trims(monkeypatch):
    monkeypatch.setenv("HOSTS", "a.com, b.com ,,")
    assert env_list("HOSTS") == ["a.com", "b.com"]


def test_parse_database_url():
    d = parse_database_url("postgres://u:p%40ss@db.host:5433/deals")
    assert (d["USER"], d["PASSWORD"], d["HOST"], d["PORT"], d["NAME"]) == (
        "u", "p@ss", "db.host", "5433", "deals")
