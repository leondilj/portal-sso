from __future__ import annotations

from fastapi import Request
from fastapi.responses import RedirectResponse

from app.sessions import FLASH_SECRET_COOKIE_NAME

_AVISO_PADRAO = "Copie agora - esse valor nao sera mostrado de novo."


def redirect_com_segredo(
    request: Request, *, destino: str, titulo: str, valor: str, voltar_url: str
) -> RedirectResponse:
    """POST-redirect-GET: grava o segredo num cookie flash de vida curta
    (~5min) e redireciona pra rota GET que vai revela-lo exatamente uma
    vez. Usado tanto para client_secret novo/regenerado quanto para senha
    inicial/resetada de usuario (app/sessions.py's OneTimeSecretCookie)."""
    flash = request.app.state.flash_secret_cookie
    cookie_value = flash.encode(
        {"titulo": titulo, "valor": valor, "aviso": _AVISO_PADRAO, "voltar_url": voltar_url}
    )
    settings = request.app.state.settings
    response = RedirectResponse(url=destino, status_code=303)
    response.set_cookie(
        FLASH_SECRET_COOKIE_NAME,
        cookie_value,
        max_age=300,
        httponly=True,
        secure=settings.portal_cookie_secure,
        samesite="lax",
    )
    return response


def read_flash_secret(request: Request) -> dict[str, str] | None:
    """So le/decodifica - quem chama e responsavel por, na resposta final,
    chamar response.delete_cookie(FLASH_SECRET_COOKIE_NAME) (mesmo se isso
    devolver None), pra que um refresh na pagina de revelacao nunca mostre
    o valor de novo."""
    flash = request.app.state.flash_secret_cookie
    cookie_value = request.cookies.get(FLASH_SECRET_COOKIE_NAME)
    if cookie_value is None:
        return None
    return flash.decode(cookie_value)
