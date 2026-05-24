import pytest
from pydantic import ValidationError

from saveatrain_mcp.config import Settings

REQUIRED_ENV = {
    "SAT_API_BASE_URL": "https://vendor.example.com",
    "SAT_AGENT_EMAIL": "agent@example.com",
    "SAT_AGENT_TOKEN": "tok_abc",
    "SAT_FORWARDED_FOR": "203.0.113.5",
    "MONGO_URI": "mongodb://localhost:27017",
}


def _clear_env(monkeypatch):
    for k in REQUIRED_ENV:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.delenv("MONGO_DB", raising=False)
    monkeypatch.delenv("SAT_MCP_ENV_FILE", raising=False)


def test_settings_raises_when_required_env_missing(monkeypatch, tmp_path):
    _clear_env(monkeypatch)
    # Point env_file at a non-existent file so .env in CWD isn't read.
    monkeypatch.setenv("SAT_MCP_ENV_FILE", str(tmp_path / "nope.env"))

    with pytest.raises(ValidationError) as exc:
        Settings()

    missing = {e["loc"][0] for e in exc.value.errors()}
    assert {
        "sat_api_base_url",
        "sat_agent_email",
        "sat_agent_token",
        "sat_forwarded_for",
        "mongo_uri",
    } <= missing


def test_settings_loads_from_env(monkeypatch, tmp_path):
    _clear_env(monkeypatch)
    monkeypatch.setenv("SAT_MCP_ENV_FILE", str(tmp_path / "nope.env"))
    for k, v in REQUIRED_ENV.items():
        monkeypatch.setenv(k, v)

    s = Settings()
    assert str(s.sat_api_base_url).rstrip("/") == "https://vendor.example.com"
    assert s.sat_agent_email == "agent@example.com"
    assert s.sat_agent_token.get_secret_value() == "tok_abc"
    assert s.sat_forwarded_for == "203.0.113.5"
    assert s.mongo_uri == "mongodb://localhost:27017"
    assert s.mongo_db == "sat"  # default
