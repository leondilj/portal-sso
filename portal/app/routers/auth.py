from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from app.jwt_verify import InvalidTokenError, extract_acessos
from app.sessions import SESSION_COOKIE_NAME, SessionData
from app.supabase_client import InvalidCredentialsError

router = APIRouter()


@router.post("/login")
async def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
) -> Response:
    templates: Jinja2Templates = request.app.state.templates
    try:
        session = await request.app.state.supabase_client.password_login(email, password)
        claims = request.app.state.jwks_verifier.verify(session.access_token)
    except (InvalidCredentialsError, InvalidTokenError):
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": "e-mail ou senha invalidos"},
            status_code=200,
        )

    session_data = SessionData(
        user_id=session.user_id,
        email=session.email,
        access_token=session.access_token,
        refresh_token=session.refresh_token,
        acessos=extract_acessos(claims),
    )
    cookie_value = request.app.state.session_manager.encode(session_data)
    settings = request.app.state.settings

    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie(
        SESSION_COOKIE_NAME,
        cookie_value,
        max_age=settings.portal_session_max_age_seconds,
        httponly=True,
        secure=settings.portal_cookie_secure,
        samesite="lax",
    )
    return response


@router.post("/logout")
async def logout() -> RedirectResponse:
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE_NAME)
    return response


@router.get("/login")
async def login_form(request: Request):
    templates: Jinja2Templates = request.app.state.templates
    return templates.TemplateResponse(request, "login.html", {"error": None})
