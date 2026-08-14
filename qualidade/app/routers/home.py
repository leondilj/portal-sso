from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.deps import get_current_session
from app.sessions import SESSION_COOKIE_NAME, SessionData

router = APIRouter()


@router.get("/")
async def home(
    request: Request, session: Annotated[SessionData | None, Depends(get_current_session)]
):
    templates: Jinja2Templates = request.app.state.templates
    return templates.TemplateResponse(request, "home.html", {"session": session})


@router.get("/area-gerente")
async def area_gerente(
    request: Request, session: Annotated[SessionData | None, Depends(get_current_session)]
):
    if session is None or "gerente" not in session.papeis:
        raise HTTPException(status_code=403, detail="area restrita a gerentes de Qualidade")
    templates: Jinja2Templates = request.app.state.templates
    return templates.TemplateResponse(request, "area-gerente.html", {"session": session})


@router.get("/logout")
async def logout() -> RedirectResponse:
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie(SESSION_COOKIE_NAME)
    return response
