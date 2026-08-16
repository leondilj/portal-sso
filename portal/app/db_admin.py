from __future__ import annotations

from typing import Any

import asyncpg

from app.db import Queryable
from app.models import (
    AplicacaoRow,
    AppClientSummary,
    AuthUserRow,
    PapelComAplicacaoRow,
    PapelRow,
    UsuarioPapelRow,
)


class DuplicateAplicacaoIdError(Exception):
    def __init__(self, aplicacao_id: str) -> None:
        self.aplicacao_id = aplicacao_id
        super().__init__(aplicacao_id)


class DuplicateCodigoError(Exception):
    def __init__(self, aplicacao_id: str, codigo: str) -> None:
        self.aplicacao_id = aplicacao_id
        self.codigo = codigo
        super().__init__(f"{aplicacao_id}/{codigo}")


def _stringify_uuid_fields(row: dict[str, Any], *fields: str) -> dict[str, Any]:
    """asyncpg decodifica colunas `uuid` como objetos uuid.UUID, nao str -
    igual ao bug ja corrigido em db.consume_auth_code (auth_codes.user_id).
    Toda linha construida aqui que passa por um campo `uuid` do Postgres
    precisa desse tratamento antes de virar um modelo pydantic (que espera
    str)."""
    for field in fields:
        if row.get(field) is not None:
            row[field] = str(row[field])
    return row


# --- Sistemas (aplicacoes) --------------------------------------------


async def list_aplicacoes(pool: Queryable) -> list[AplicacaoRow]:
    rows = await pool.fetch(
        """
        select id, nome, descricao, url, icone, ativo, ordem, criado_em
        from public.aplicacoes
        order by ordem, nome
        """
    )
    return [AplicacaoRow(**dict(row)) for row in rows]


async def fetch_aplicacao(pool: Queryable, aplicacao_id: str) -> AplicacaoRow | None:
    row = await pool.fetchrow(
        """
        select id, nome, descricao, url, icone, ativo, ordem, criado_em
        from public.aplicacoes where id = $1
        """,
        aplicacao_id,
    )
    return AplicacaoRow(**dict(row)) if row else None


async def create_aplicacao(
    pool: Queryable,
    *,
    aplicacao_id: str,
    nome: str,
    descricao: str | None,
    url: str,
    icone: str | None,
    ordem: int,
) -> None:
    try:
        await pool.execute(
            """
            insert into public.aplicacoes (id, nome, descricao, url, icone, ordem)
            values ($1, $2, $3, $4, $5, $6)
            """,
            aplicacao_id,
            nome,
            descricao,
            url,
            icone,
            ordem,
        )
    except asyncpg.UniqueViolationError as exc:
        raise DuplicateAplicacaoIdError(aplicacao_id) from exc


async def update_aplicacao(
    pool: Queryable,
    *,
    aplicacao_id: str,
    nome: str,
    descricao: str | None,
    url: str,
    icone: str | None,
    ordem: int,
) -> None:
    await pool.execute(
        """
        update public.aplicacoes
        set nome = $2, descricao = $3, url = $4, icone = $5, ordem = $6
        where id = $1
        """,
        aplicacao_id,
        nome,
        descricao,
        url,
        icone,
        ordem,
    )


async def set_aplicacao_ativo(pool: Queryable, aplicacao_id: str, ativo: bool) -> None:
    await pool.execute(
        "update public.aplicacoes set ativo = $2 where id = $1", aplicacao_id, ativo
    )


# --- Perfis (papeis), por sistema --------------------------------------


async def list_papeis(pool: Queryable, aplicacao_id: str) -> list[PapelRow]:
    rows = await pool.fetch(
        """
        select id, aplicacao_id, codigo, nome, descricao, criado_em
        from public.papeis where aplicacao_id = $1
        order by codigo
        """,
        aplicacao_id,
    )
    return [PapelRow(**_stringify_uuid_fields(dict(row), "id")) for row in rows]


async def fetch_papel(pool: Queryable, papel_id: str) -> PapelRow | None:
    row = await pool.fetchrow(
        """
        select id, aplicacao_id, codigo, nome, descricao, criado_em
        from public.papeis where id = $1
        """,
        papel_id,
    )
    return PapelRow(**_stringify_uuid_fields(dict(row), "id")) if row else None


async def create_papel(
    pool: Queryable, *, aplicacao_id: str, codigo: str, nome: str, descricao: str | None
) -> PapelRow:
    try:
        row = await pool.fetchrow(
            """
            insert into public.papeis (aplicacao_id, codigo, nome, descricao)
            values ($1, $2, $3, $4)
            returning id, aplicacao_id, codigo, nome, descricao, criado_em
            """,
            aplicacao_id,
            codigo,
            nome,
            descricao,
        )
    except asyncpg.UniqueViolationError as exc:
        raise DuplicateCodigoError(aplicacao_id, codigo) from exc
    assert row is not None
    return PapelRow(**_stringify_uuid_fields(dict(row), "id"))


async def update_papel(
    pool: Queryable, *, papel_id: str, nome: str, descricao: str | None
) -> None:
    # `codigo` e intencionalmente imutavel apos criado: e a chave que
    # aparece em app_metadata.acessos no JWT de todo app cliente (README
    # secao 7.3) - editar silenciosamente quebraria qualquer app cliente
    # que dependa desse codigo, sem nenhum sinal no portal. Renomear = criar
    # um papel novo e apagar o antigo, de proposito.
    await pool.execute(
        "update public.papeis set nome = $2, descricao = $3 where id = $1",
        papel_id,
        nome,
        descricao,
    )


async def count_usuarios_com_papel(pool: Queryable, papel_id: str) -> int:
    row = await pool.fetchrow(
        "select count(*) as total from public.usuario_papeis where papel_id = $1",
        papel_id,
    )
    return int(row["total"]) if row else 0


async def delete_papel(pool: Queryable, papel_id: str) -> None:
    await pool.execute("delete from public.papeis where id = $1", papel_id)


# --- Client credentials (app_clients) -----------------------------------
# Leituras administrativas NUNCA selecionam client_secret - ver
# AppClientSummary. O segredo so existe em memoria durante o request que o
# gera/regenera (routers/admin/clientes.py), nunca num request de leitura.


async def fetch_app_client_summary(
    pool: Queryable, aplicacao_id: str
) -> AppClientSummary | None:
    row = await pool.fetchrow(
        "select aplicacao_id, redirect_uris from public.app_clients where aplicacao_id = $1",
        aplicacao_id,
    )
    if row is None:
        return None
    data = dict(row)
    return AppClientSummary(
        aplicacao_id=data["aplicacao_id"], redirect_uris=data["redirect_uris"], has_secret=True
    )


async def set_app_client(
    pool: Queryable, *, aplicacao_id: str, redirect_uris: list[str], client_secret: str
) -> None:
    """Upsert usado tanto para configurar um sistema como cliente OAuth pela
    primeira vez quanto para regenerar o secret - a unica diferenca e o
    valor de client_secret passado pelo chamador."""
    await pool.execute(
        """
        insert into public.app_clients (aplicacao_id, client_secret, redirect_uris)
        values ($1, $2, $3)
        on conflict (aplicacao_id) do update
          set client_secret = excluded.client_secret,
              redirect_uris = excluded.redirect_uris
        """,
        aplicacao_id,
        client_secret,
        redirect_uris,
    )


async def update_app_client_redirect_uris(
    pool: Queryable, *, aplicacao_id: str, redirect_uris: list[str]
) -> None:
    """Edita so as redirect_uris, sem tocar no secret - separado de
    set_app_client de proposito, pra corrigir um typo de URL nunca poder
    rotacionar o secret sem querer."""
    await pool.execute(
        "update public.app_clients set redirect_uris = $2 where aplicacao_id = $1",
        aplicacao_id,
        redirect_uris,
    )


# --- Usuarios (auth.users, leitura direta) ------------------------------
# auth.users e do GoTrue, fora do schema public - o portal so le (via essa
# conexao asyncpg privilegiada); toda escrita (criar usuario, resetar
# senha) passa pela Admin API (app/supabase_admin_client.py), nunca por SQL
# direto aqui.


async def search_auth_users(
    pool: Queryable, query: str | None, limit: int = 50
) -> list[AuthUserRow]:
    rows = await pool.fetch(
        """
        select id, email, created_at, last_sign_in_at, email_confirmed_at
        from auth.users
        where ($1::text is null or email ilike '%' || $1 || '%')
        order by created_at desc
        limit $2
        """,
        query,
        limit,
    )
    return [AuthUserRow(**_stringify_uuid_fields(dict(row), "id")) for row in rows]


async def fetch_auth_user(pool: Queryable, user_id: str) -> AuthUserRow | None:
    row = await pool.fetchrow(
        """
        select id, email, created_at, last_sign_in_at, email_confirmed_at
        from auth.users where id = $1
        """,
        user_id,
    )
    return AuthUserRow(**_stringify_uuid_fields(dict(row), "id")) if row else None


async def list_papeis_do_usuario(pool: Queryable, user_id: str) -> list[UsuarioPapelRow]:
    rows = await pool.fetch(
        """
        select up.papel_id, p.aplicacao_id, a.nome as aplicacao_nome,
               p.codigo, p.nome, up.concedido_em
        from public.usuario_papeis up
        join public.papeis p on p.id = up.papel_id
        join public.aplicacoes a on a.id = p.aplicacao_id
        where up.user_id = $1
        order by a.nome, p.codigo
        """,
        user_id,
    )
    return [UsuarioPapelRow(**_stringify_uuid_fields(dict(row), "papel_id")) for row in rows]


async def list_papeis_disponiveis(pool: Queryable) -> list[PapelComAplicacaoRow]:
    rows = await pool.fetch(
        """
        select p.id, p.aplicacao_id, a.nome as aplicacao_nome, p.codigo,
               p.nome, p.descricao, p.criado_em
        from public.papeis p
        join public.aplicacoes a on a.id = p.aplicacao_id
        order by a.nome, p.codigo
        """
    )
    return [PapelComAplicacaoRow(**_stringify_uuid_fields(dict(row), "id")) for row in rows]


async def grant_papel(pool: Queryable, *, user_id: str, papel_id: str, concedido_por: str) -> None:
    await pool.execute(
        """
        insert into public.usuario_papeis (user_id, papel_id, concedido_por)
        values ($1, $2, $3)
        on conflict (user_id, papel_id) do nothing
        """,
        user_id,
        papel_id,
        concedido_por,
    )


async def revoke_papel(pool: Queryable, *, user_id: str, papel_id: str) -> None:
    await pool.execute(
        "delete from public.usuario_papeis where user_id = $1 and papel_id = $2",
        user_id,
        papel_id,
    )
