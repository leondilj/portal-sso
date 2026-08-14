import pytest
from pydantic import ValidationError

from app.config import Settings


def test_settings_loads_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "http://supabase.example")
    monkeypatch.setenv("SUPABASE_PUBLISHABLE_KEY", "anon-key")
    monkeypatch.setenv("SUPABASE_JWKS_URL", "http://supabase.example/jwks.json")
    monkeypatch.setenv("PORTAL_DATABASE_URL", "postgresql://u:p@host/db")
    monkeypatch.setenv("PORTAL_SESSION_SECRET", "s3cr3t")

    settings = Settings(_env_file=None)

    assert settings.supabase_url == "http://supabase.example"
    assert settings.portal_database_url == "postgresql://u:p@host/db"
    # defaults nao sobrescritos pelo ambiente
    assert settings.portal_session_max_age_seconds == 1800
    assert settings.portal_port == 8080


def test_settings_missing_required_var_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_PUBLISHABLE_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_JWKS_URL", raising=False)
    monkeypatch.delenv("PORTAL_DATABASE_URL", raising=False)
    monkeypatch.delenv("PORTAL_SESSION_SECRET", raising=False)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)
