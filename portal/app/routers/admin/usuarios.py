from __future__ import annotations

import secrets

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from app import db_admin as da
from app.deps import (
    ADMIN_APP_ID,
    ADMIN_ROLE_CODE,
    AdminClientDep,
    AdminSession,
    CurrentSession,
    PoolDep,
)
from app.models import AuthUserRow
from app.routers.admin._flash import read_flash_secret, redirect_com_segredo
from app.sessions import FLASH_SECRET_COOKIE_NAME
from app.supabase_admin_client import AdminApiError, EmailAlreadyExistsError, WeakPasswordError

router = APIRouter(prefix="/usuarios")


async def _fetch_usuario_ou_404(pool: object, user_id: str) -> AuthUserRow:
    usuario = await da.fetch_auth_user(pool, user_id)  # type: ignore[arg-type]
    if usuario is None:
        raise HTTPException(status_code=404, detail="usuario nao encontrado")
    return usuario


async def _render_detalhe(
    request: Request,
    pool: object,
    user_id: str,
    *,
    session: AdminSession,
    error: str | None = None,
) -> Response:
    templates: Jinja2Templates = request.app.state.templates
    usuario = await _fetch_usuario_ou_404(pool, user_id)
    papeis = await da.list_papeis_do_usuario(pool, user_id)  # type: ignore[arg-type]
    papeis_disponiveis = await da.list_papeis_disponiveis(pool)  # type: ignore[arg-type]
    return templates.TemplateResponse(
        request,
        "admin/usuario_detalhe.html",
        {
            "usuario": usuario,
            "papeis": papeis,
            "papeis_disponiveis": papeis_disponiveis,
            "error": error,
            "session": session,
        },
    )


@router.get("")
async def buscar(
    request: Request, *, pool: PoolDep, session: AdminSession, q: str | None = None
) -> Response:
    templates: Jinja2Templates = request.app.state.templates
    resultados = await da.search_auth_users(pool, q, 50) if q else []
    return templates.TemplateResponse(
        request,
        "admin/usuarios_busca.html",
        {"q": q or "", "resultados": resultados, "session": session},
    )


@router.get("/novo")
async def novo_form(request: Request, *, pool: PoolDep, session: AdminSession) -> Response:
    templates: Jinja2Templates = request.app.state.templates
    papeis_disponiveis = await da.list_papeis_disponiveis(pool)
    return templates.TemplateResponse(
        request,
        "admin/usuario_novo.html",
        {
            "papeis_disponiveis": papeis_disponiveis,
            "error": None,
            "busca_url": None,
            "session": session,
        },
    )


@router.post("/novo")
async def criar(
    request: Request,
    *,
    pool: PoolDep,
    admin_client: AdminClientDep,
    session: CurrentSession,
    email: str = Form(...),
    nome: str = Form(""),
    papel_inicial: str = Form(""),
) -> Response:
    """A senha inicial e gerada pelo sistema (nao digitada pelo admin), no
    mesmo espirito do client_secret - revelada uma unica vez logo em
    seguida. O GoTrue ja faz o hash; o portal so segura o plaintext em
    memoria durante este request + a janela curta do cookie flash."""
    templates: Jinja2Templates = request.app.state.templates
    senha_gerada = secrets.token_urlsafe(16)

    try:
        criado = await admin_client.create_user(
            email=email, password=senha_gerada, nome=nome or None
        )
    except EmailAlreadyExistsError:
        papeis_disponiveis = await da.list_papeis_disponiveis(pool)
        return templates.TemplateResponse(
            request,
            "admin/usuario_novo.html",
            {
                "papeis_disponiveis": papeis_disponiveis,
                "error": f"ja existe um usuario com o e-mail {email}",
                "busca_url": f"/admin/usuarios?q={email}",
                "session": session,
            },
        )
    except WeakPasswordError as exc:
        papeis_disponiveis = await da.list_papeis_disponiveis(pool)
        return templates.TemplateResponse(
            request,
            "admin/usuario_novo.html",
            {
                "papeis_disponiveis": papeis_disponiveis,
                "error": "senha gerada rejeitada pelo Supabase: " + "; ".join(exc.reasons),
                "busca_url": None,
                "session": session,
            },
        )
    except AdminApiError:
        papeis_disponiveis = await da.list_papeis_disponiveis(pool)
        return templates.TemplateResponse(
            request,
            "admin/usuario_novo.html",
            {
                "papeis_disponiveis": papeis_disponiveis,
                "error": "erro ao criar usuario, tente novamente",
                "busca_url": None,
                "session": session,
            },
        )

    if papel_inicial:
        await da.grant_papel(
            pool, user_id=criado.id, papel_id=papel_inicial, concedido_por=session.user_id
        )

    return redirect_com_segredo(
        request,
        destino=f"/admin/usuarios/{criado.id}/segredo",
        titulo="Usuario criado - senha inicial",
        valor=senha_gerada,
        voltar_url=f"/admin/usuarios/{criado.id}",
    )


@router.get("/{user_id}")
async def detalhe(
    user_id: str, request: Request, *, pool: PoolDep, session: AdminSession
) -> Response:
    return await _render_detalhe(request, pool, user_id, session=session)


@router.post("/{user_id}/papeis/conceder")
async def conceder_papel(
    user_id: str,
    request: Request,
    *,
    pool: PoolDep,
    session: CurrentSession,
    papel_id: str = Form(...),
) -> Response:
    await da.grant_papel(pool, user_id=user_id, papel_id=papel_id, concedido_por=session.user_id)
    return RedirectResponse(url=f"/admin/usuarios/{user_id}", status_code=303)


@router.post("/{user_id}/papeis/{papel_id}/revogar")
async def revogar_papel(
    user_id: str, papel_id: str, request: Request, *, pool: PoolDep, session: AdminSession
) -> Response:
    papel = await da.fetch_papel(pool, papel_id)
    e_papel_admin_do_portal = (
        papel is not None and papel.aplicacao_id == ADMIN_APP_ID and papel.codigo == ADMIN_ROLE_CODE
    )
    if e_papel_admin_do_portal:
        total = await da.count_usuarios_com_papel(pool, papel_id)
        if total <= 1:
            return await _render_detalhe(
                request,
                pool,
                user_id,
                session=session,
                error=(
                    "Nao e possivel revogar: este e o ultimo administrador do portal. "
                    "Promova outro usuario a admin antes de revogar este."
                ),
            )
    await da.revoke_papel(pool, user_id=user_id, papel_id=papel_id)
    return RedirectResponse(url=f"/admin/usuarios/{user_id}", status_code=303)


@router.post("/{user_id}/redefinir-senha")
async def redefinir_senha(
    user_id: str,
    request: Request,
    *,
    pool: PoolDep,
    admin_client: AdminClientDep,
    session: AdminSession,
) -> Response:
    await _fetch_usuario_ou_404(pool, user_id)
    nova_senha = secrets.token_urlsafe(16)
    try:
        await admin_client.reset_password(user_id=user_id, new_password=nova_senha)
    except WeakPasswordError as exc:
        return await _render_detalhe(
            request,
            pool,
            user_id,
            session=session,
            error="senha gerada rejeitada: " + "; ".join(exc.reasons),
        )
    except AdminApiError:
        return await _render_detalhe(
            request,
            pool,
            user_id,
            session=session,
            error="erro ao redefinir senha, tente novamente",
        )

    return redirect_com_segredo(
        request,
        destino=f"/admin/usuarios/{user_id}/segredo",
        titulo="Senha redefinida",
        valor=nova_senha,
        voltar_url=f"/admin/usuarios/{user_id}",
    )


@router.get("/{user_id}/segredo")
async def segredo(user_id: str, request: Request, *, session: AdminSession) -> Response:
    templates: Jinja2Templates = request.app.state.templates
    payload = read_flash_secret(request)
    response = templates.TemplateResponse(
        request, "admin/segredo_revelado.html", {"segredo": payload, "session": session}
    )
    response.delete_cookie(FLASH_SECRET_COOKIE_NAME)
    return response
