from __future__ import annotations

from dataclasses import dataclass

from supabase import AsyncClient, acreate_client


class InvalidCredentialsError(Exception):
    pass


@dataclass
class SupabaseSession:
    user_id: str
    email: str | None
    access_token: str
    refresh_token: str | None


class SupabaseAuthClient:
    """Wrapper fino sobre supabase-py, usado SO para login/refresh (GoTrue).

    Todo o resto do acesso a dados do portal passa por app/db.py (asyncpg
    direto), nao por este cliente / PostgREST.
    """

    def __init__(self, url: str, publishable_key: str) -> None:
        self._url = url
        self._key = publishable_key
        self._client: AsyncClient | None = None

    async def _get_client(self) -> AsyncClient:
        if self._client is None:
            self._client = await acreate_client(self._url, self._key)
        return self._client

    async def password_login(self, email: str, password: str) -> SupabaseSession:
        client = await self._get_client()
        try:
            result = await client.auth.sign_in_with_password(
                {"email": email, "password": password}
            )
        except Exception as exc:  # supabase-py raises its own AuthApiError etc.
            raise InvalidCredentialsError(str(exc)) from exc

        if result.session is None or result.user is None:
            raise InvalidCredentialsError("login sem sessao retornada")

        return SupabaseSession(
            user_id=result.user.id,
            email=result.user.email,
            access_token=result.session.access_token,
            refresh_token=result.session.refresh_token,
        )
