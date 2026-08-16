from __future__ import annotations

import secrets

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from app import db_admin as da
from app.deps import PoolDep
from app.models import AplicacaoRow
from app.routers.admin._flash import read_flash_secret, redirect_com_segredo
from app.sessions import FLASH_SECRET_COOKIE_NAME

router = APIRouter(prefix="/sistemas/{aplicacao_id}/cliente")


async def _fetch_sistema_ou_404(pool: object, aplicacao_id: str) -> AplicacaoRow:
    sistema = await da.fetch_aplicacao(pool, aplicacao_id)  # type: ignore[arg-type]
    if sistema is None:
        raise HTTPException(status_code=404, detail="sistema nao encontrado")
    return sistema


@router.get("/novo")
async def configurar_form(aplicacao_id: str, request: Request, *, pool: PoolDep) -> Response:
    templates: Jinja2Templates = request.app.state.templates
    sistema = await _fetch_sistema_ou_404(pool, aplicacao_id)
    if await da.fetch_app_client_summary(pool, aplicacao_id) is not None:
        return RedirectResponse(url=f"/admin/sistemas/{aplicacao_id}", status_code=303)
    return templates.TemplateResponse(
        request,
        "admin/cliente_form.html",
        {"sistema": sistema, "redirect_uri": "", "acao": "Configurar", "error": None},
    )


@router.post("/novo")
async def configurar(
    aplicacao_id: str, request: Request, *, pool: PoolDep, redirect_uri: str = Form(...)
) -> Response:
    await _fetch_sistema_ou_404(pool, aplicacao_id)
    client_secret = secrets.token_urlsafe(32)
    await da.set_app_client(
        pool, aplicacao_id=aplicacao_id, redirect_uris=[redirect_uri], client_secret=client_secret
    )
    return redirect_com_segredo(
        request,
        destino=f"/admin/sistemas/{aplicacao_id}/cliente/segredo",
        titulo="Client secret gerado",
        valor=client_secret,
        voltar_url=f"/admin/sistemas/{aplicacao_id}",
    )


@router.get("/editar")
async def editar_form(aplicacao_id: str, request: Request, *, pool: PoolDep) -> Response:
    templates: Jinja2Templates = request.app.state.templates
    sistema = await _fetch_sistema_ou_404(pool, aplicacao_id)
    cliente = await da.fetch_app_client_summary(pool, aplicacao_id)
    if cliente is None:
        raise HTTPException(status_code=404, detail="sistema ainda nao configurado como cliente")
    return templates.TemplateResponse(
        request,
        "admin/cliente_form.html",
        {
            "sistema": sistema,
            "redirect_uri": cliente.redirect_uris[0] if cliente.redirect_uris else "",
            "acao": "Salvar",
            "error": None,
        },
    )


@router.post("/editar")
async def editar(
    aplicacao_id: str, request: Request, *, pool: PoolDep, redirect_uri: str = Form(...)
) -> RedirectResponse:
    await _fetch_sistema_ou_404(pool, aplicacao_id)
    await da.update_app_client_redirect_uris(
        pool, aplicacao_id=aplicacao_id, redirect_uris=[redirect_uri]
    )
    return RedirectResponse(url=f"/admin/sistemas/{aplicacao_id}", status_code=303)


@router.get("/regenerar")
async def regenerar_confirmar(aplicacao_id: str, request: Request, *, pool: PoolDep) -> Response:
    templates: Jinja2Templates = request.app.state.templates
    sistema = await _fetch_sistema_ou_404(pool, aplicacao_id)
    cliente = await da.fetch_app_client_summary(pool, aplicacao_id)
    if cliente is None:
        raise HTTPException(status_code=404, detail="sistema ainda nao configurado como cliente")
    return templates.TemplateResponse(
        request, "admin/cliente_confirmar_regenerar.html", {"sistema": sistema}
    )


@router.post("/regenerar")
async def regenerar(aplicacao_id: str, request: Request, *, pool: PoolDep) -> Response:
    cliente = await da.fetch_app_client_summary(pool, aplicacao_id)
    if cliente is None:
        raise HTTPException(status_code=404, detail="sistema ainda nao configurado como cliente")
    client_secret = secrets.token_urlsafe(32)
    await da.set_app_client(
        pool,
        aplicacao_id=aplicacao_id,
        redirect_uris=cliente.redirect_uris,
        client_secret=client_secret,
    )
    return redirect_com_segredo(
        request,
        destino=f"/admin/sistemas/{aplicacao_id}/cliente/segredo",
        titulo="Client secret regenerado",
        valor=client_secret,
        voltar_url=f"/admin/sistemas/{aplicacao_id}",
    )


@router.get("/segredo")
async def segredo(aplicacao_id: str, request: Request) -> Response:
    templates: Jinja2Templates = request.app.state.templates
    payload = read_flash_secret(request)
    response = templates.TemplateResponse(
        request, "admin/segredo_revelado.html", {"segredo": payload}
    )
    response.delete_cookie(FLASH_SECRET_COOKIE_NAME)
    return response
