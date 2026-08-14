from __future__ import annotations

from dataclasses import dataclass

import httpx


class TokenExchangeError(Exception):
    """Erro ao trocar o code pelo token no portal.

    `error` e o codigo devolvido pelo portal (invalid_grant, expired,
    already_used, invalid_client) ou um valor sintetico ("network_error",
    "unknown_error") se a chamada nem chegou a completar direito.
    """

    def __init__(self, error: str) -> None:
        self.error = error
        super().__init__(error)


@dataclass
class PortalToken:
    access_token: str
    refresh_token: str | None


class PortalClient:
    """Fala com o POST /token do portal para trocar um authorization code
    pelo token do Supabase - a metade "aplicacao cliente" do fluxo descrito
    no README secao 8."""

    def __init__(self, token_url: str, client_secret: str) -> None:
        self._token_url = token_url
        self._client_secret = client_secret

    async def exchange_code(self, code: str) -> PortalToken:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    self._token_url,
                    json={"code": code, "client_secret": self._client_secret},
                )
        except httpx.RequestError as exc:
            raise TokenExchangeError("network_error") from exc

        if response.status_code != 200:
            error = "unknown_error"
            try:
                error = response.json().get("error", error)
            except ValueError:
                pass
            raise TokenExchangeError(error)

        body = response.json()
        return PortalToken(
            access_token=body["access_token"], refresh_token=body.get("refresh_token")
        )
