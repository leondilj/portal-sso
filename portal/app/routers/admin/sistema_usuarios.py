from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from app import db_admin as da
from app.deps import AdminSession, PoolDep
from app.models import AplicacaoRow

router = APIRouter(prefix="/sistemas/{aplicacao_id}/usuarios")


async def _fetch_sistema_ou_404(pool: object, aplicacao_id: str) -> AplicacaoRow:
    sistema = await da.fetch_aplicacao(pool, aplicacao_id)  # type: ignore[arg-type]
    if sistema is None:
        raise HTTPException(status_code=404, detail="sistema nao encontrado")
    return sistema


@router.get("")
async def listar(
    aplicacao_id: str, request: Request, *, pool: PoolDep, session: AdminSession
) -> Response:
    templates: Jinja2Templates = request.app.state.templates
    sistema = await _fetch_sistema_ou_404(pool, aplicacao_id)
    usuarios = await da.list_usuarios_do_sistema(pool, aplicacao_id)
    return templates.TemplateResponse(
        request,
        "admin/sistema_usuarios.html",
        {"sistema": sistema, "usuarios": usuarios, "session": session},
    )


@router.post("/{user_id}/papeis/{papel_id}/revogar")
async def revogar(aplicacao_id: str, user_id: str, papel_id: str, *, pool: PoolDep) -> Response:
    await da.revoke_papel(pool, user_id=user_id, papel_id=papel_id)
    return RedirectResponse(url=f"/admin/sistemas/{aplicacao_id}/usuarios", status_code=303)
