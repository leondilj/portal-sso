from __future__ import annotations

from dataclasses import dataclass

from supabase import AsyncClient, acreate_client
from supabase_auth.errors import AuthApiError, AuthWeakPasswordError

_DUPLICATE_EMAIL_CODES = {"email_exists", "user_already_exists"}


class AdminApiError(Exception):
    pass


class EmailAlreadyExistsError(AdminApiError):
    pass


class WeakPasswordError(AdminApiError):
    def __init__(self, reasons: list[str]) -> None:
        self.reasons = reasons
        super().__init__(", ".join(reasons))


@dataclass
class AdminCreatedUser:
    id: str
    email: str | None


class SupabaseAdminClient:
    """Wrapper fino sobre a Admin API do GoTrue (supabase-py), usada SO
    pela area /admin para criar usuarios e resetar senha.

    Classe SEPARADA de SupabaseAuthClient (nao uma extensao): o AsyncClient
    do supabase-py fixa a apikey no construtor, entao um client construido
    com a publishable key nao pode fazer chamadas admin - precisa de uma
    instancia propria construida com a service_role key (SUPABASE_SECRET_KEY),
    uma credencial categoricamente mais sensivel.
    """

    def __init__(self, url: str, secret_key: str) -> None:
        self._url = url
        self._key = secret_key
        self._client: AsyncClient | None = None

    async def _get_client(self) -> AsyncClient:
        if self._client is None:
            self._client = await acreate_client(self._url, self._key)
        return self._client

    async def create_user(self, *, email: str, password: str) -> AdminCreatedUser:
        """Cria um usuario ja confirmado (email_confirm=True), sem depender
        de SMTP - o lab nao tem envio de e-mail configurado, entao um fluxo
        de convite por link nao entregaria nada."""
        client = await self._get_client()
        try:
            result = await client.auth.admin.create_user(
                {"email": email, "password": password, "email_confirm": True}
            )
        except AuthWeakPasswordError as exc:
            raise WeakPasswordError(exc.reasons) from exc
        except AuthApiError as exc:
            if exc.code in _DUPLICATE_EMAIL_CODES:
                raise EmailAlreadyExistsError(email) from exc
            raise AdminApiError(exc.message) from exc

        return AdminCreatedUser(id=result.user.id, email=result.user.email)

    async def reset_password(self, *, user_id: str, new_password: str) -> None:
        client = await self._get_client()
        try:
            await client.auth.admin.update_user_by_id(user_id, {"password": new_password})
        except AuthWeakPasswordError as exc:
            raise WeakPasswordError(exc.reasons) from exc
        except AuthApiError as exc:
            raise AdminApiError(exc.message) from exc
