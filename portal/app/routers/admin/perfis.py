from __future__ import annotations

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from app import db_admin as da
from app.deps import PoolDep
from app.models import AplicacaoRow, PapelRow

router = APIRouter(prefix="/sistemas/{aplicacao_id}/perfis")


async def _fetch_sistema_ou_404(pool: object, aplicacao_id: str) -> AplicacaoRow:
    sistema = await da.fetch_aplicacao(pool, aplicacao_id)  # type: ignore[arg-type]
    if sistema is None:
        raise HTTPException(status_code=404, detail="sistema nao encontrado")
    return sistema


async def _fetch_papel_ou_404(pool: object, papel_id: str) -> PapelRow:
    papel = await da.fetch_papel(pool, papel_id)  # type: ignore[arg-type]
    if papel is None:
        raise HTTPException(status_code=404, detail="perfil nao encontrado")
    return papel


@router.get("")
async def listar(aplicacao_id: str, request: Request, *, pool: PoolDep) -> Response:
    templates: Jinja2Templates = request.app.state.templates
    sistema = await _fetch_sistema_ou_404(pool, aplicacao_id)
    perfis = await da.list_papeis(pool, aplicacao_id)
    return templates.TemplateResponse(
        request, "admin/perfis_lista.html", {"sistema": sistema, "perfis": perfis}
    )


@router.get("/novo")
async def novo_form(aplicacao_id: str, request: Request, *, pool: PoolDep) -> Response:
    templates: Jinja2Templates = request.app.state.templates
    sistema = await _fetch_sistema_ou_404(pool, aplicacao_id)
    return templates.TemplateResponse(
        request, "admin/perfil_form.html", {"sistema": sistema, "papel": None, "error": None}
    )


@router.post("/novo")
async def criar(
    aplicacao_id: str,
    request: Request,
    *,
    pool: PoolDep,
    codigo: str = Form(...),
    nome: str = Form(...),
    descricao: str = Form(""),
) -> Response:
    templates: Jinja2Templates = request.app.state.templates
    sistema = await _fetch_sistema_ou_404(pool, aplicacao_id)
    try:
        await da.create_papel(
            pool, aplicacao_id=aplicacao_id, codigo=codigo, nome=nome, descricao=descricao or None
        )
    except da.DuplicateCodigoError:
        return templates.TemplateResponse(
            request,
            "admin/perfil_form.html",
            {
                "sistema": sistema,
                "papel": None,
                "error": f"ja existe um perfil com o codigo '{codigo}' neste sistema",
            },
        )
    return RedirectResponse(url=f"/admin/sistemas/{aplicacao_id}/perfis", status_code=303)


@router.get("/{papel_id}/editar")
async def editar_form(
    aplicacao_id: str, papel_id: str, request: Request, *, pool: PoolDep
) -> Response:
    templates: Jinja2Templates = request.app.state.templates
    sistema = await _fetch_sistema_ou_404(pool, aplicacao_id)
    papel = await _fetch_papel_ou_404(pool, papel_id)
    return templates.TemplateResponse(
        request, "admin/perfil_form.html", {"sistema": sistema, "papel": papel, "error": None}
    )


@router.post("/{papel_id}/editar")
async def editar(
    aplicacao_id: str,
    papel_id: str,
    *,
    pool: PoolDep,
    nome: str = Form(...),
    descricao: str = Form(""),
) -> RedirectResponse:
    await _fetch_papel_ou_404(pool, papel_id)
    await da.update_papel(pool, papel_id=papel_id, nome=nome, descricao=descricao or None)
    return RedirectResponse(url=f"/admin/sistemas/{aplicacao_id}/perfis", status_code=303)


@router.get("/{papel_id}/excluir")
async def excluir_confirmar(
    aplicacao_id: str, papel_id: str, request: Request, *, pool: PoolDep
) -> Response:
    templates: Jinja2Templates = request.app.state.templates
    sistema = await _fetch_sistema_ou_404(pool, aplicacao_id)
    papel = await _fetch_papel_ou_404(pool, papel_id)
    total_usuarios = await da.count_usuarios_com_papel(pool, papel_id)
    return templates.TemplateResponse(
        request,
        "admin/perfil_confirmar_exclusao.html",
        {"sistema": sistema, "papel": papel, "total_usuarios": total_usuarios},
    )


@router.post("/{papel_id}/excluir")
async def excluir(aplicacao_id: str, papel_id: str, *, pool: PoolDep) -> RedirectResponse:
    await _fetch_papel_ou_404(pool, papel_id)
    await da.delete_papel(pool, papel_id)
    return RedirectResponse(url=f"/admin/sistemas/{aplicacao_id}/perfis", status_code=303)
