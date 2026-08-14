from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

# Precisa estar setado ANTES de importar app.main, porque o import executa
# `app = create_app()` no nivel do modulo (o alvo que `uvicorn app.main:app`
# espera encontrar), o que constroi um Settings() a partir do ambiente.
os.environ.setdefault("PORTAL_TOKEN_URL", "http://portal.invalid/token")
os.environ.setdefault("QUALIDADE_CLIENT_SECRET", "module-level-test-secret")
os.environ.setdefault("SUPABASE_JWKS_URL", "http://supabase.invalid/jwks.json")
os.environ.setdefault("QUALIDADE_SESSION_SECRET", "module-level-session-secret")

import jwt  # noqa: E402
import pytest  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import ec  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402
from app.sessions import SESSION_COOKIE_NAME, SessionData  # noqa: E402

# --- JWT / JWKS de teste --------------------------------------------------


@pytest.fixture
def ec_keys():
    private_key = ec.generate_private_key(ec.SECP256R1())
    return private_key, private_key.public_key()


@pytest.fixture
def sign_jwt(ec_keys):
    private_key, _ = ec_keys

    def _sign(claims: dict[str, Any] | None = None, **overrides: Any) -> str:
        payload: dict[str, Any] = {
            "sub": "user-1",
            "email": "joao@lab.internal",
            "aud": "authenticated",
            "role": "authenticated",
            "exp": datetime.now(UTC) + timedelta(minutes=30),
        }
        payload.update(claims or {})
        payload.update(overrides)
        return jwt.encode(payload, private_key, algorithm="ES256", headers={"kid": "test"})

    return _sign


class FakeJWKClient:
    def __init__(self, public_key: Any) -> None:
        self._public_key = public_key

    def get_signing_key_from_jwt(self, token: str) -> SimpleNamespace:
        return SimpleNamespace(key=self._public_key)


# --- App / TestClient --------------------------------------------------


@pytest.fixture
def test_settings() -> Settings:
    return Settings(
        portal_token_url="http://portal.test/token",
        qualidade_client_secret="segredo-certo",
        supabase_jwks_url="http://supabase.test/jwks.json",
        qualidade_session_secret="test-session-secret",
        qualidade_session_max_age_seconds=1800,
        qualidade_cookie_secure=False,
    )


@dataclass
class Harness:
    app: Any
    client: TestClient

    def set_session(self, session: SessionData) -> None:
        cookie_value = self.app.state.session_manager.encode(session)
        self.client.cookies.set(SESSION_COOKIE_NAME, cookie_value)


@pytest.fixture
def harness(test_settings: Settings, ec_keys):
    _, public_key = ec_keys

    app = create_app(settings=test_settings)
    app.state.jwks_verifier._jwk_client = FakeJWKClient(public_key)

    with TestClient(app) as client:
        yield Harness(app=app, client=client)
