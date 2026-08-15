from __future__ import annotations

import hmac
from datetime import UTC, datetime
from typing import Any, Protocol

import asyncpg

from app.models import AppClient, AppTile, AuthCodeRow


class Queryable(Protocol):
    """Subset of the asyncpg Pool/Connection interface this module needs.

    Lets the same query functions run against a real asyncpg pool/connection
    or against a lightweight in-memory fake used by the test suite.
    """

    async def fetch(self, query: str, *args: Any) -> list[Any]: ...
    async def fetchrow(self, query: str, *args: Any) -> Any | None: ...
    async def execute(self, query: str, *args: Any) -> str: ...


class AuthCodeError(Exception):
    """Base class for /token failures tied to a specific auth_codes row."""


class AuthCodeNotFoundError(AuthCodeError):
    pass


class AuthCodeAlreadyUsedError(AuthCodeError):
    pass


class AuthCodeExpiredError(AuthCodeError):
    pass


class InvalidClientSecretError(AuthCodeError):
    pass


async def create_pool(dsn: str) -> asyncpg.Pool:
    return await asyncpg.create_pool(dsn)


async def fetch_apps_for_acessos(pool: Queryable, acessos: dict) -> list[AppTile]:
    app_ids = list(acessos.keys())
    if not app_ids:
        return []
    rows = await pool.fetch(
        """
        select id, nome, descricao, url, icone
        from public.aplicacoes
        where id = any($1::text[]) and ativo = true
        order by ordem, nome
        """,
        app_ids,
    )
    return [AppTile(**dict(row)) for row in rows]


async def fetch_app_client(pool: Queryable, aplicacao_id: str) -> AppClient | None:
    row = await pool.fetchrow(
        """
        select aplicacao_id, client_secret, redirect_uris
        from public.app_clients where aplicacao_id = $1
        """,
        aplicacao_id,
    )
    return AppClient(**dict(row)) if row else None


async def insert_auth_code(
    pool: Queryable,
    *,
    code: str,
    user_id: str,
    aplicacao_id: str,
    redirect_uri: str,
    access_token: str,
    refresh_token: str | None,
    expira_em: datetime,
) -> None:
    await pool.execute(
        """
        insert into public.auth_codes
            (code, user_id, aplicacao_id, redirect_uri, access_token, refresh_token, expira_em)
        values ($1, $2, $3, $4, $5, $6, $7)
        """,
        code,
        user_id,
        aplicacao_id,
        redirect_uri,
        access_token,
        refresh_token,
        expira_em,
    )


async def consume_auth_code(pool: Any, code: str, client_secret: str) -> AuthCodeRow:
    """Valida e marca um auth_code como usado, de forma atomica.

    Ordem importante: o client_secret e validado ANTES de marcar usado_em.
    Se a ordem fosse invertida, um chute de secret errado bastaria para
    queimar um code legitimo (nega servico a um request concorrente
    legitimo). A trava de linha (`for update`) garante que duas trocas
    concorrentes do mesmo code nunca vencem as duas.
    """
    async with pool.acquire() as conn, conn.transaction():
        row = await conn.fetchrow(
            "select * from public.auth_codes where code = $1 for update",
            code,
        )
        if row is None:
            raise AuthCodeNotFoundError(code)
        if row["usado_em"] is not None:
            raise AuthCodeAlreadyUsedError(code)
        if row["expira_em"] <= datetime.now(UTC):
            raise AuthCodeExpiredError(code)

        client = await fetch_app_client(conn, row["aplicacao_id"])
        if client is None or not hmac.compare_digest(client.client_secret, client_secret):
            raise InvalidClientSecretError(code)

        await conn.execute(
            "update public.auth_codes set usado_em = now() where code = $1",
            code,
        )
        row_data = dict(row)
        row_data["user_id"] = str(row_data["user_id"])
        return AuthCodeRow(**row_data)
