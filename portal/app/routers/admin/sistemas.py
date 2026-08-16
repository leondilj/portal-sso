from __future__ import annotations

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from app import db_admin as da
from app.deps import AdminSession, PoolDep

router = APIRouter(prefix="/sistemas")


@router.get("")
async def listar(request: Request, *, pool: PoolDep, session: AdminSession) -> Response:
    templates: Jinja2Templates = request.app.state.templates
    sistemas = await da.list_aplicacoes(pool)
    return templates.TemplateResponse(
        request, "admin/sistemas_lista.html", {"sistemas": sistemas, "session": session}
    )


@router.get("/novo")
async def novo_form(request: Request, *, session: AdminSession) -> Response:
    templates: Jinja2Templates = request.app.state.templates
    return templates.TemplateResponse(
        request, "admin/sistema_novo.html", {"error": None, "session": session}
    )


@router.post("/novo")
async def criar(
    request: Request,
    *,
    pool: PoolDep,
    session: AdminSession,
    aplicacao_id: str = Form(...),
    nome: str = Form(...),
    descricao: str = Form(""),
    url: str = Form(...),
    icone: str = Form(""),
    ordem: int = Form(0),
) -> Response:
    templates: Jinja2Templates = request.app.state.templates
    try:
        await da.create_aplicacao(
            pool,
            aplicacao_id=aplicacao_id,
            nome=nome,
            descricao=descricao or None,
            url=url,
            icone=icone or None,
            ordem=ordem,
        )
    except da.DuplicateAplicacaoIdError:
        return templates.TemplateResponse(
            request,
            "admin/sistema_novo.html",
            {
                "error": f"ja existe um sistema com o id '{aplicacao_id}'",
                "session": session,
            },
            status_code=200,
        )
    return RedirectResponse(url=f"/admin/sistemas/{aplicacao_id}", status_code=303)


@router.get("/{aplicacao_id}")
async def detalhe(
    aplicacao_id: str, request: Request, *, pool: PoolDep, session: AdminSession
) -> Response:
    templates: Jinja2Templates = request.app.state.templates
    sistema = await da.fetch_aplicacao(pool, aplicacao_id)
    if sistema is None:
        raise HTTPException(status_code=404, detail="sistema nao encontrado")
    cliente = await da.fetch_app_client_summary(pool, aplicacao_id)
    perfis = await da.list_papeis(pool, aplicacao_id)
    return templates.TemplateResponse(
        request,
        "admin/sistema_detalhe.html",
        {"sistema": sistema, "cliente": cliente, "perfis": perfis, "session": session},
    )


@router.post("/{aplicacao_id}")
async def atualizar(
    aplicacao_id: str,
    request: Request,
    *,
    pool: PoolDep,
    nome: str = Form(...),
    descricao: str = Form(""),
    url: str = Form(...),
    icone: str = Form(""),
    ordem: int = Form(0),
) -> RedirectResponse:
    await da.update_aplicacao(
        pool,
        aplicacao_id=aplicacao_id,
        nome=nome,
        descricao=descricao or None,
        url=url,
        icone=icone or None,
        ordem=ordem,
    )
    return RedirectResponse(url=f"/admin/sistemas/{aplicacao_id}", status_code=303)


@router.post("/{aplicacao_id}/ativar")
async def ativar(aplicacao_id: str, *, pool: PoolDep) -> RedirectResponse:
    await da.set_aplicacao_ativo(pool, aplicacao_id, True)
    return RedirectResponse(url=f"/admin/sistemas/{aplicacao_id}", status_code=303)


@router.post("/{aplicacao_id}/desativar")
async def desativar(aplicacao_id: str, *, pool: PoolDep) -> RedirectResponse:
    await da.set_aplicacao_ativo(pool, aplicacao_id, False)
    return RedirectResponse(url=f"/admin/sistemas/{aplicacao_id}", status_code=303)
