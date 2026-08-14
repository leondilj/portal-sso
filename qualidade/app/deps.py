from __future__ import annotations

from fastapi import Request

from app.sessions import SESSION_COOKIE_NAME, SessionData


def get_current_session(request: Request) -> SessionData | None:
    """Ao contrario do portal, aqui a ausencia de sessao NAO e um erro/redirect
    - essa app nao tem pagina de login propria (login sempre acontece no
    portal). GET / decide o que mostrar quando isso vier None."""
    cookie_value = request.cookies.get(SESSION_COOKIE_NAME)
    if cookie_value is None:
        return None
    session_manager = request.app.state.session_manager
    return session_manager.decode(cookie_value)
