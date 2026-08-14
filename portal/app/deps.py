from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request

from app.sessions import SESSION_COOKIE_NAME, SessionData


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
