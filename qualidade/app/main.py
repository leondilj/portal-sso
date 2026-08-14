from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import Settings
from app.jwt_verify import JWKSVerifier
from app.portal_client import PortalClient
from app.routers import callback, home
from app.sessions import SessionManager

BASE_DIR = Path(__file__).resolve().parent.parent


def create_app(settings: Settings | None = None) -> FastAPI:
    # Settings() sem argumentos le tudo do ambiente/.env - os campos nao tem
    # default em Python porque sao obrigatorios via env var, entao o mypy os
    # ve como parametros faltando; e o comportamento pretendido em runtime.
    settings = settings or Settings()  # type: ignore[call-arg]

    app = FastAPI(title="Qualidade (app cliente de exemplo do Portal SSO)")
    app.state.settings = settings
    app.state.templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
    app.state.jwks_verifier = JWKSVerifier(settings.supabase_jwks_url)
    app.state.portal_client = PortalClient(
        settings.portal_token_url, settings.qualidade_client_secret
    )
    app.state.session_manager = SessionManager(
        settings.qualidade_session_secret, settings.qualidade_session_max_age_seconds
    )

    app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
    app.include_router(callback.router)
    app.include_router(home.router)

    return app


app = create_app()
