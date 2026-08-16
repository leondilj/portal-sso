from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates

from app.deps import AdminSession, require_admin
from app.routers.admin import clientes, perfis, sistemas, usuarios

router = APIRouter(prefix="/admin", dependencies=[Depends(require_admin)])
router.include_router(sistemas.router)
router.include_router(clientes.router)
router.include_router(perfis.router)
router.include_router(usuarios.router)


@router.get("")
async def dashboard(request: Request, session: AdminSession):
    templates: Jinja2Templates = request.app.state.templates
    return templates.TemplateResponse(request, "admin/dashboard.html", {"session": session})
