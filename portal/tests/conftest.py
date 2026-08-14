from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

# Precisa estar setado ANTES de importar app.main, porque o import executa
# `app = create_app()` no nivel do modulo (o alvo que `uvicorn app.main:app`
# espera encontrar), o que constroi um Settings() a partir do ambiente.
os.environ.setdefault("SUPABASE_URL", "http://supabase.invalid")
os.environ.setdefault("SUPABASE_PUBLISHABLE_KEY", "module-level-test-key")
os.environ.setdefault(
    "SUPABASE_JWKS_URL", "http://supabase.invalid/auth/v1/.well-known/jwks.json"
)
os.environ.setdefault("PORTAL_DATABASE_URL", "postgresql://test/test")
os.environ.setdefault("PORTAL_SESSION_SECRET", "module-level-test-secret")

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
    """Substitui PyJWKClient nos testes: sem fetch de rede, so devolve a
    chave publica de teste."""

    def __init__(self, public_key: Any) -> None:
        self._public_key = public_key

    def get_signing_key_from_jwt(self, token: str) -> SimpleNamespace:
        return SimpleNamespace(key=self._public_key)


# --- Fake asyncpg pool -----------------------------------------------------


class _AcquireCtx:
    def __init__(self, pool: FakePool) -> None:
        self._pool = pool

    async def __aenter__(self) -> FakeConnection:
        return FakeConnection(self._pool)

    async def __aexit__(self, *exc: Any) -> bool:
        return False


class _FakeTransaction:
    def __init__(self, pool: FakePool) -> None:
        self._pool = pool

    async def __aenter__(self) -> _FakeTransaction:
        await self._pool._lock.acquire()
        return self

    async def __aexit__(self, *exc: Any) -> bool:
        self._pool._lock.release()
        return False


class FakeConnection:
    def __init__(self, pool: FakePool) -> None:
        self._pool = pool

    async def fetch(self, query: str, *args: Any) -> list[dict]:
        return self._pool._dispatch_fetch(query, args)

    async def fetchrow(self, query: str, *args: Any) -> dict | None:
        rows = self._pool._dispatch_fetch(query, args)
        return rows[0] if rows else None

    async def execute(self, query: str, *args: Any) -> str:
        return self._pool._dispatch_execute(query, args)

    def transaction(self) -> _FakeTransaction:
        return _FakeTransaction(self._pool)


class FakePool:
    """Fake minimo do subset de asyncpg.Pool usado por app/db.py, guardando
    tudo em dicts em memoria. O lock global emula o `for update` do Postgres
    o bastante para provar a protecao contra replay em corrida."""

    def __init__(self) -> None:
        self.aplicacoes: dict[str, dict] = {}
        self.app_clients: dict[str, dict] = {}
        self.auth_codes: dict[str, dict] = {}
        self._lock = asyncio.Lock()

    def acquire(self) -> _AcquireCtx:
        return _AcquireCtx(self)

    async def fetch(self, query: str, *args: Any) -> list[dict]:
        return self._dispatch_fetch(query, args)

    async def fetchrow(self, query: str, *args: Any) -> dict | None:
        rows = self._dispatch_fetch(query, args)
        return rows[0] if rows else None

    async def execute(self, query: str, *args: Any) -> str:
        return self._dispatch_execute(query, args)

    def _dispatch_fetch(self, query: str, args: tuple) -> list[dict]:
        if "from public.aplicacoes" in query:
            ids = set(args[0])
            rows = [r for r in self.aplicacoes.values() if r["id"] in ids and r["ativo"]]
            rows.sort(key=lambda r: (r["ordem"], r["nome"]))
            return [dict(r) for r in rows]
        if "from public.app_clients" in query:
            row = self.app_clients.get(args[0])
            return [dict(row)] if row else []
        if "from public.auth_codes" in query and "for update" in query:
            row = self.auth_codes.get(args[0])
            return [dict(row)] if row else []
        raise NotImplementedError(query)

    def _dispatch_execute(self, query: str, args: tuple) -> str:
        if "insert into public.auth_codes" in query:
            (
                code,
                user_id,
                aplicacao_id,
                redirect_uri,
                access_token,
                refresh_token,
                expira_em,
            ) = args
            self.auth_codes[code] = {
                "code": code,
                "user_id": user_id,
                "aplicacao_id": aplicacao_id,
                "redirect_uri": redirect_uri,
                "access_token": access_token,
                "refresh_token": refresh_token,
                "expira_em": expira_em,
                "usado_em": None,
            }
            return "INSERT 1"
        if "update public.auth_codes set usado_em" in query:
            self.auth_codes[args[0]]["usado_em"] = datetime.now(UTC)
            return "UPDATE 1"
        raise NotImplementedError(query)


@pytest.fixture
def fake_pool() -> FakePool:
    pool = FakePool()
    pool.aplicacoes["qualidade"] = {
        "id": "qualidade",
        "nome": "Qualidade",
        "descricao": "Controle de qualidade",
        "url": "http://qualidade.lab.internal",
        "icone": None,
        "ativo": True,
        "ordem": 1,
    }
    pool.aplicacoes["vendas"] = {
        "id": "vendas",
        "nome": "Vendas",
        "descricao": "Pedidos",
        "url": "http://vendas.lab.internal",
        "icone": None,
        "ativo": True,
        "ordem": 2,
    }
    pool.aplicacoes["inativa"] = {
        "id": "inativa",
        "nome": "Inativa",
        "descricao": None,
        "url": "http://inativa.lab.internal",
        "icone": None,
        "ativo": False,
        "ordem": 3,
    }
    pool.app_clients["qualidade"] = {
        "aplicacao_id": "qualidade",
        "client_secret": "segredo-certo",
        "redirect_uris": ["http://qualidade.lab.internal/callback"],
    }
    return pool


# --- App / TestClient --------------------------------------------------


@pytest.fixture
def test_settings() -> Settings:
    return Settings(
        supabase_url="http://supabase.test",
        supabase_publishable_key="test-anon-key",
        supabase_jwks_url="http://supabase.test/auth/v1/.well-known/jwks.json",
        portal_database_url="postgresql://test/test",
        portal_session_secret="test-session-secret",
        portal_session_max_age_seconds=1800,
        portal_cookie_secure=False,
        portal_auth_code_ttl_seconds=60,
    )


@dataclass
class Harness:
    app: Any
    client: TestClient

    def set_session(self, session: SessionData) -> None:
        cookie_value = self.app.state.session_manager.encode(session)
        self.client.cookies.set(SESSION_COOKIE_NAME, cookie_value)


@pytest.fixture
def harness(test_settings: Settings, fake_pool: FakePool, ec_keys):
    _, public_key = ec_keys

    async def fake_pool_factory(dsn: str) -> FakePool:
        return fake_pool

    app = create_app(settings=test_settings, db_pool_factory=fake_pool_factory)
    app.state.jwks_verifier._jwk_client = FakeJWKClient(public_key)

    with TestClient(app) as client:
        yield Harness(app=app, client=client)
