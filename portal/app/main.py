from __future__ import annotations

from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app import db
from app.config import Settings
from app.jwt_verify import JWKSVerifier
from app.routers import auth, home, oauth
from app.sessions import SessionManager
from app.supabase_client import SupabaseAuthClient

BASE_DIR = Path(__file__).resolve().parent.parent

PoolFactory = Callable[[str], Awaitable[Any]]


def create_app(
    settings: Settings | None = None,
    db_pool_factory: PoolFactory = db.create_pool,
) -> FastAPI:
    """App factory.

    `db_pool_factory` e injetavel para que os testes possam substituir o
    pool asyncpg real por um fake em memoria, sem precisar de um Postgres
    de verdade.
    """
    # Settings() sem argumentos le tudo do ambiente/.env - os campos nao tem
    # default em Python porque sao obrigatorios via env var, entao o mypy os
    # ve como parametros faltando; e o comportamento pretendido em runtime.
    settings = settings or Settings()  # type: ignore[call-arg]

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.db_pool = await db_pool_factory(settings.portal_database_url)
        yield
        close = getattr(app.state.db_pool, "close", None)
        if close is not None:
            await close()

    app = FastAPI(title="Portal SSO", lifespan=lifespan)
    app.state.settings = settings
    app.state.templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
    app.state.jwks_verifier = JWKSVerifier(settings.supabase_jwks_url)
    app.state.supabase_client = SupabaseAuthClient(
        settings.supabase_url, settings.supabase_publishable_key
    )
    app.state.session_manager = SessionManager(
        settings.portal_session_secret, settings.portal_session_max_age_seconds
    )

    app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
    app.include_router(auth.router)
    app.include_router(home.router)
    app.include_router(oauth.router)

    return app


app = create_app()
