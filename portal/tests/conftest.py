from __future__ import annotations

import asyncio
import json
import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import asyncpg

# Precisa estar setado ANTES de importar app.main, porque o import executa
# `app = create_app()` no nivel do modulo (o alvo que `uvicorn app.main:app`
# espera encontrar), o que constroi um Settings() a partir do ambiente.
os.environ.setdefault("SUPABASE_URL", "http://supabase.invalid")
os.environ.setdefault("SUPABASE_PUBLISHABLE_KEY", "module-level-test-key")
os.environ.setdefault(
    "SUPABASE_JWKS_URL", "http://supabase.invalid/auth/v1/.well-known/jwks.json"
)
os.environ.setdefault("SUPABASE_SECRET_KEY", "module-level-test-secret-key")
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
    """Fake minimo do subset de asyncpg.Pool usado por app/db.py e
    app/db_admin.py, guardando tudo em dicts em memoria. O lock global
    emula o `for update` do Postgres o bastante para provar a protecao
    contra replay em corrida no /token.

    Dispatch organizado por tabela (um metodo `_fetch_<tabela>`/inserts
    dedicados) em vez de uma unica cadeia if/elif - a area admin sozinha
    já passa de uma dezena de formatos de query, o que ficaria ilegivel
    num chain so.
    """

    def __init__(self) -> None:
        self.aplicacoes: dict[str, dict] = {}
        self.app_clients: dict[str, dict] = {}
        self.auth_codes: dict[str, dict] = {}
        self.papeis: dict[str, dict] = {}
        self.usuario_papeis: dict[tuple[str, str], dict] = {}
        self.auth_users: dict[str, dict] = {}
        self.profiles: dict[str, dict] = {}
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

    # --- fetch -----------------------------------------------------------

    def _dispatch_fetch(self, query: str, args: tuple) -> list[dict]:
        if "jsonb_agg" in query:
            # list_usuarios_do_sistema: unica query que agrega papeis por
            # usuario num jsonb - checada antes do catch-all "from
            # auth.users" abaixo, que tambem apareceria aqui.
            return self._fetch_usuarios_do_sistema(args)
        if "insert into public.papeis" in query:
            # create_papel usa `insert ... returning`, via fetchrow.
            return self._insert_papel_returning(args)
        if "from public.aplicacoes" in query:
            return self._fetch_aplicacoes(query, args)
        if "from public.app_clients" in query:
            return self._fetch_app_clients(query, args)
        if "from public.auth_codes" in query:
            return self._fetch_auth_codes(args)
        if "from public.usuario_papeis" in query:
            return self._fetch_usuario_papeis(query, args)
        if "from public.papeis" in query:
            return self._fetch_papeis(query, args)
        if "from auth.users" in query:
            return self._fetch_auth_users(query, args)
        raise NotImplementedError(query)

    def _fetch_aplicacoes(self, query: str, args: tuple) -> list[dict]:
        if "any($1" in query:
            # fetch_apps_for_acessos: inner join com app_clients - so
            # aparece como tile quem esta de fato configurado como cliente
            # OAuth (ver app/db.py).
            ids = set(args[0])
            rows = [
                r
                for r in self.aplicacoes.values()
                if r["id"] in ids and r["ativo"] and r["id"] in self.app_clients
            ]
            rows.sort(key=lambda r: (r["ordem"], r["nome"]))
            return [dict(r) for r in rows]
        if "where id = $1" in query:
            row = self.aplicacoes.get(args[0])
            return [dict(row)] if row else []
        # list_aplicacoes (admin): sem where, todas as linhas
        rows = sorted(self.aplicacoes.values(), key=lambda r: (r["ordem"], r["nome"]))
        return [dict(r) for r in rows]

    def _fetch_app_clients(self, query: str, args: tuple) -> list[dict]:
        row = self.app_clients.get(args[0])
        if row is None:
            return []
        if "client_secret" in query:
            return [dict(row)]
        # fetch_app_client_summary: nunca seleciona o secret
        return [{"aplicacao_id": row["aplicacao_id"], "redirect_uris": row["redirect_uris"]}]

    def _fetch_auth_codes(self, args: tuple) -> list[dict]:
        row = self.auth_codes.get(args[0])
        return [dict(row)] if row else []

    def _fetch_papeis(self, query: str, args: tuple) -> list[dict]:
        if "join public.aplicacoes" in query:
            # list_papeis_disponiveis: todos os papeis, com nome da app
            rows = []
            for papel in self.papeis.values():
                app = self.aplicacoes.get(papel["aplicacao_id"])
                rows.append({**papel, "aplicacao_nome": app["nome"] if app else None})
            rows.sort(key=lambda r: (r["aplicacao_nome"] or "", r["codigo"]))
            return rows
        if "where aplicacao_id = $1" in query:
            rows = [p for p in self.papeis.values() if p["aplicacao_id"] == args[0]]
            rows.sort(key=lambda r: r["codigo"])
            return [dict(r) for r in rows]
        if "where id = $1" in query:
            row = self.papeis.get(args[0])
            return [dict(row)] if row else []
        raise NotImplementedError(query)

    def _fetch_usuario_papeis(self, query: str, args: tuple) -> list[dict]:
        if "count(*)" in query:
            total = sum(1 for key in self.usuario_papeis if key[1] == args[0])
            return [{"total": total}]
        # list_papeis_do_usuario
        rows = []
        for (user_id, papel_id), vinculo in self.usuario_papeis.items():
            if user_id != args[0]:
                continue
            papel = self.papeis[papel_id]
            app = self.aplicacoes[papel["aplicacao_id"]]
            rows.append(
                {
                    "papel_id": papel_id,
                    "aplicacao_id": papel["aplicacao_id"],
                    "aplicacao_nome": app["nome"],
                    "codigo": papel["codigo"],
                    "nome": papel["nome"],
                    "concedido_em": vinculo["concedido_em"],
                }
            )
        rows.sort(key=lambda r: (r["aplicacao_nome"], r["codigo"]))
        return rows

    def _nome_do_profile(self, user_id: str) -> str | None:
        profile = self.profiles.get(user_id)
        return profile["nome"] if profile else None

    def _fetch_auth_users(self, query: str, args: tuple) -> list[dict]:
        if "id = $1" in query:
            row = self.auth_users.get(args[0])
            if row is None:
                return []
            return [{**row, "nome": self._nome_do_profile(args[0])}]
        # search_auth_users
        termo, limite = args
        rows = list(self.auth_users.values())
        if termo:
            rows = [r for r in rows if termo.lower() in (r["email"] or "").lower()]
        rows.sort(key=lambda r: r["created_at"], reverse=True)
        return [{**r, "nome": self._nome_do_profile(r["id"])} for r in rows[:limite]]

    def _fetch_usuarios_do_sistema(self, args: tuple) -> list[dict]:
        (aplicacao_id,) = args
        papeis_por_usuario: dict[str, list[dict]] = {}
        for (user_id, papel_id), _vinculo in self.usuario_papeis.items():
            papel = self.papeis.get(papel_id)
            if papel is None or papel["aplicacao_id"] != aplicacao_id:
                continue
            papeis_por_usuario.setdefault(user_id, []).append(
                {"papel_id": papel_id, "codigo": papel["codigo"], "nome": papel["nome"]}
            )
        rows = []
        for user_id, papeis in papeis_por_usuario.items():
            user = self.auth_users.get(user_id)
            if user is None:
                continue
            papeis.sort(key=lambda p: p["codigo"])
            rows.append(
                {
                    "id": user_id,
                    "email": user["email"],
                    "nome": self._nome_do_profile(user_id),
                    "papeis": json.dumps(papeis),
                }
            )
        rows.sort(key=lambda r: r["nome"] or r["email"] or "")
        return rows

    def _insert_papel_returning(self, args: tuple) -> list[dict]:
        aplicacao_id, codigo, nome, descricao = args
        duplicado = any(
            p["aplicacao_id"] == aplicacao_id and p["codigo"] == codigo
            for p in self.papeis.values()
        )
        if duplicado:
            raise asyncpg.UniqueViolationError(f"duplicate codigo: {aplicacao_id}/{codigo}")
        papel_id = str(uuid.uuid4())
        row = {
            "id": papel_id,
            "aplicacao_id": aplicacao_id,
            "codigo": codigo,
            "nome": nome,
            "descricao": descricao,
            "criado_em": datetime.now(UTC),
        }
        self.papeis[papel_id] = row
        return [dict(row)]

    # --- execute -----------------------------------------------------------

    def _dispatch_execute(self, query: str, args: tuple) -> str:
        if "insert into public.auth_codes" in query:
            return self._insert_auth_code(args)
        if "update public.auth_codes set usado_em" in query:
            self.auth_codes[args[0]]["usado_em"] = datetime.now(UTC)
            return "UPDATE 1"
        if "insert into public.aplicacoes" in query:
            return self._insert_aplicacao(args)
        if "update public.aplicacoes" in query and "set nome" in query:
            aplicacao_id, nome, descricao, url, icone, ordem = args
            self.aplicacoes[aplicacao_id].update(
                nome=nome, descricao=descricao, url=url, icone=icone, ordem=ordem
            )
            return "UPDATE 1"
        if "update public.aplicacoes set ativo" in query:
            aplicacao_id, ativo = args
            self.aplicacoes[aplicacao_id]["ativo"] = ativo
            return "UPDATE 1"
        if "update public.papeis set nome" in query:
            papel_id, nome, descricao = args
            self.papeis[papel_id].update(nome=nome, descricao=descricao)
            return "UPDATE 1"
        if "delete from public.papeis" in query:
            papel_id = args[0]
            self.papeis.pop(papel_id, None)
            for key in [k for k in self.usuario_papeis if k[1] == papel_id]:
                del self.usuario_papeis[key]
            return "DELETE 1"
        if "insert into public.app_clients" in query:
            aplicacao_id, client_secret, redirect_uris = args
            self.app_clients[aplicacao_id] = {
                "aplicacao_id": aplicacao_id,
                "client_secret": client_secret,
                "redirect_uris": redirect_uris,
            }
            return "INSERT 1"
        if "update public.app_clients set redirect_uris" in query:
            aplicacao_id, redirect_uris = args
            self.app_clients[aplicacao_id]["redirect_uris"] = redirect_uris
            return "UPDATE 1"
        if "insert into public.usuario_papeis" in query:
            user_id, papel_id, concedido_por = args
            key = (user_id, papel_id)
            if key not in self.usuario_papeis:
                self.usuario_papeis[key] = {
                    "user_id": user_id,
                    "papel_id": papel_id,
                    "concedido_por": concedido_por,
                    "concedido_em": datetime.now(UTC),
                }
            return "INSERT 1"
        if "delete from public.usuario_papeis" in query:
            user_id, papel_id = args
            self.usuario_papeis.pop((user_id, papel_id), None)
            return "DELETE 1"
        raise NotImplementedError(query)

    def _insert_auth_code(self, args: tuple) -> str:
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

    def _insert_aplicacao(self, args: tuple) -> str:
        aplicacao_id, nome, descricao, url, icone, ordem = args
        if aplicacao_id in self.aplicacoes:
            raise asyncpg.UniqueViolationError(f"duplicate key: {aplicacao_id}")
        self.aplicacoes[aplicacao_id] = {
            "id": aplicacao_id,
            "nome": nome,
            "descricao": descricao,
            "url": url,
            "icone": icone,
            "ativo": True,
            "ordem": ordem,
            "criado_em": datetime.now(UTC),
        }
        return "INSERT 1"


@pytest.fixture
def fake_pool() -> FakePool:
    pool = FakePool()
    agora = datetime.now(UTC)
    pool.aplicacoes["qualidade"] = {
        "id": "qualidade",
        "nome": "Qualidade",
        "descricao": "Controle de qualidade",
        "url": "http://qualidade.lab.internal",
        "icone": None,
        "ativo": True,
        "ordem": 1,
        "criado_em": agora,
    }
    pool.aplicacoes["vendas"] = {
        "id": "vendas",
        "nome": "Vendas",
        "descricao": "Pedidos",
        "url": "http://vendas.lab.internal",
        "icone": None,
        "ativo": True,
        "ordem": 2,
        "criado_em": agora,
    }
    pool.aplicacoes["inativa"] = {
        "id": "inativa",
        "nome": "Inativa",
        "descricao": None,
        "url": "http://inativa.lab.internal",
        "icone": None,
        "ativo": False,
        "ordem": 3,
        "criado_em": agora,
    }
    # ativa e presente em acessos, mas SEM app_clients - caso real do
    # proprio "portal" (nao e um app cliente redirecionado via /authorize).
    # Nao deve aparecer como tile clicavel (regressao coberta em
    # test_home_router.py).
    pool.aplicacoes["semcliente"] = {
        "id": "semcliente",
        "nome": "SemCliente",
        "descricao": None,
        "url": "http://semcliente.lab.internal",
        "icone": None,
        "ativo": True,
        "ordem": 4,
        "criado_em": agora,
    }
    # o proprio portal (sql/0005_admin_role.sql) - ativo=true, sem
    # app_clients, mesma forma de "semcliente" acima mas com o id real
    # usado por ADMIN_APP_ID (app/deps.py) e pelos testes de usuario_papeis.
    pool.aplicacoes["portal"] = {
        "id": "portal",
        "nome": "Portal SSO",
        "descricao": "Area administrativa do proprio portal",
        "url": "/",
        "icone": None,
        "ativo": True,
        "ordem": 0,
        "criado_em": agora,
    }
    pool.app_clients["qualidade"] = {
        "aplicacao_id": "qualidade",
        "client_secret": "segredo-certo",
        "redirect_uris": ["http://qualidade.lab.internal/callback"],
    }
    pool.app_clients["vendas"] = {
        "aplicacao_id": "vendas",
        "client_secret": "segredo-vendas",
        "redirect_uris": ["http://vendas.lab.internal/callback"],
    }
    return pool


# --- App / TestClient --------------------------------------------------


@pytest.fixture
def test_settings() -> Settings:
    return Settings(
        supabase_url="http://supabase.test",
        supabase_publishable_key="test-anon-key",
        supabase_jwks_url="http://supabase.test/auth/v1/.well-known/jwks.json",
        supabase_secret_key="test-secret-key",
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
