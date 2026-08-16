from __future__ import annotations

from typing import Annotated, Any

from fastapi import Depends, HTTPException, Request

from app.sessions import SESSION_COOKIE_NAME, SessionData
from app.supabase_admin_client import SupabaseAdminClient

ADMIN_APP_ID = "portal"
ADMIN_ROLE_CODE = "admin"


def get_db_pool(request: Request) -> Any:
    return request.app.state.db_pool


def get_current_session(request: Request) -> SessionData:
    cookie_value = request.cookies.get(SESSION_COOKIE_NAME)
    session = None
    if cookie_value is not None:
        session = request.app.state.session_manager.decode(cookie_value)
    if session is None:
        raise HTTPException(
            status_code=303, detail="nao autenticado", headers={"Location": "/login"}
        )
    return session


def require_admin(
    session: Annotated[SessionData, Depends(get_current_session)],
) -> SessionData:
    """Compoe sobre get_current_session (nao substitui): primeiro exige
    sessao valida (303 -> /login se ausente), so depois checa o papel
    'admin' na aplicacao 'portal' - o mesmo modelo papel-por-aplicacao ja
    usado para qualidade/vendas/pcp, sem sistema de permissao paralelo (ver
    sql/0005_admin_role.sql)."""
    if ADMIN_ROLE_CODE not in session.acessos.get(ADMIN_APP_ID, []):
        raise HTTPException(status_code=403, detail="acesso restrito a administradores")
    return session


def get_supabase_admin_client(request: Request) -> SupabaseAdminClient:
    return request.app.state.supabase_admin_client


# Aliases reutilizados pelos routers, principalmente os da area /admin (que
# tem muito mais rotas por arquivo do que auth.py/home.py/oauth.py).
PoolDep = Annotated[Any, Depends(get_db_pool)]
CurrentSession = Annotated[SessionData, Depends(get_current_session)]
AdminSession = Annotated[SessionData, Depends(require_admin)]
AdminClientDep = Annotated[SupabaseAdminClient, Depends(get_supabase_admin_client)]
