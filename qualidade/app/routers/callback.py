from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from app.jwt_verify import InvalidTokenError, extract_papeis
from app.portal_client import TokenExchangeError
from app.sessions import SESSION_COOKIE_NAME, SessionData

router = APIRouter()

_EXCHANGE_ERROR_MESSAGES = {
    "invalid_grant": "Code invalido ou desconhecido.",
    "expired": "Esse code expirou. Volte ao portal e clique em Qualidade de novo.",
    "already_used": "Esse code ja foi usado. Volte ao portal e clique em Qualidade de novo.",
    "invalid_client": "Falha na configuracao desta aplicacao junto ao portal.",
    "network_error": "Nao foi possivel falar com o portal agora.",
}


@router.get("/callback")
async def callback(code: str, request: Request) -> Response:
    templates: Jinja2Templates = request.app.state.templates

    try:
        token = await request.app.state.portal_client.exchange_code(code)
    except TokenExchangeError as exc:
        message = _EXCHANGE_ERROR_MESSAGES.get(exc.error, "Nao foi possivel confirmar seu acesso.")
        return templates.TemplateResponse(
            request, "sem-acesso.html", {"message": message}, status_code=400
        )

    try:
        claims = request.app.state.jwks_verifier.verify(token.access_token)
    except InvalidTokenError:
        return templates.TemplateResponse(
            request,
            "sem-acesso.html",
            {"message": "O token recebido do portal nao pode ser validado."},
            status_code=401,
        )

    papeis = extract_papeis(claims, "qualidade")
    if not papeis:
        return templates.TemplateResponse(
            request,
            "sem-acesso.html",
            {"message": "Voce nao tem nenhum papel cadastrado para Qualidade."},
            status_code=403,
        )

    session = SessionData(user_id=claims["sub"], email=claims.get("email"), papeis=papeis)
    cookie_value = request.app.state.session_manager.encode(session)
    settings = request.app.state.settings

    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie(
        SESSION_COOKIE_NAME,
        cookie_value,
        max_age=settings.qualidade_session_max_age_seconds,
        httponly=True,
        secure=settings.qualidade_cookie_secure,
        samesite="lax",
    )
    return response
