from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates

from app import db
from app.deps import get_current_session, get_db_pool
from app.sessions import SessionData

router = APIRouter()


@router.get("/")
async def home(
    request: Request,
    session: Annotated[SessionData, Depends(get_current_session)],
    pool: Annotated[Any, Depends(get_db_pool)],
):
    templates: Jinja2Templates = request.app.state.templates
    apps = await db.fetch_apps_for_acessos(pool, session.acessos)
    return templates.TemplateResponse(
        request, "home.html", {"session": session, "apps": apps}
    )
