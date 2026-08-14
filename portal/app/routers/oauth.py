from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse

from app import db
from app.deps import get_current_session, get_db_pool
from app.models import TokenRequest, TokenResponse
from app.sessions import SessionData

router = APIRouter()


@router.get("/authorize")
async def authorize(
    app_id: str,
    request: Request,
    session: Annotated[SessionData, Depends(get_current_session)],
    pool: Annotated[Any, Depends(get_db_pool)],
) -> RedirectResponse:
    if app_id not in session.acessos:
        raise HTTPException(status_code=403, detail="sem acesso a esta aplicacao")

    client = await db.fetch_app_client(pool, app_id)
    if client is None or not client.redirect_uris:
        raise HTTPException(status_code=502, detail="aplicacao nao configurada")

    settings = request.app.state.settings
    redirect_uri = client.redirect_uris[0]
    code = secrets.token_urlsafe(32)
    expira_em = datetime.now(UTC) + timedelta(seconds=settings.portal_auth_code_ttl_seconds)

    await db.insert_auth_code(
        pool,
        code=code,
        user_id=session.user_id,
        aplicacao_id=app_id,
        redirect_uri=redirect_uri,
        access_token=session.access_token,
        refresh_token=session.refresh_token,
        expira_em=expira_em,
    )

    return RedirectResponse(url=f"{redirect_uri}?code={code}", status_code=302)


async def parse_token_request(request: Request) -> TokenRequest:
    content_type = request.headers.get("content-type", "")
    try:
        if "application/json" in content_type:
            body = await request.json()
            return TokenRequest(**body)
        form = await request.form()
        return TokenRequest(code=str(form["code"]), client_secret=str(form["client_secret"]))
    except (KeyError, ValueError) as exc:
        raise HTTPException(
            status_code=400, detail="code e client_secret sao obrigatorios"
        ) from exc


_ERROR_STATUS = {
    "invalid_client": 401,
    "invalid_grant": 400,
    "already_used": 400,
    "expired": 400,
}


@router.post("/token")
async def token(
    pool: Annotated[Any, Depends(get_db_pool)],
    token_request: Annotated[TokenRequest, Depends(parse_token_request)],
) -> JSONResponse:
    try:
        row = await db.consume_auth_code(pool, token_request.code, token_request.client_secret)
    except db.InvalidClientSecretError:
        error = "invalid_client"
    except db.AuthCodeNotFoundError:
        error = "invalid_grant"
    except db.AuthCodeAlreadyUsedError:
        error = "already_used"
    except db.AuthCodeExpiredError:
        error = "expired"
    else:
        response = TokenResponse(access_token=row.access_token, refresh_token=row.refresh_token)
        return JSONResponse(response.model_dump())

    return JSONResponse({"error": error}, status_code=_ERROR_STATUS[error])
