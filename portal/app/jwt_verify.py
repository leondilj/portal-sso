from __future__ import annotations

from typing import Any

import jwt
from fastapi import Header, HTTPException, Request
from jwt import PyJWKClient


class InvalidTokenError(Exception):
    pass


class JWKSVerifier:
    """Valida localmente tokens ES256 do Supabase via JWKS, sem round-trip
    HTTP por request (a chave publica e cacheada pelo PyJWKClient)."""

    def __init__(self, jwks_url: str) -> None:
        self._jwk_client = PyJWKClient(jwks_url)

    def verify(self, token: str) -> dict[str, Any]:
        try:
            signing_key = self._jwk_client.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["ES256"],
                audience="authenticated",
            )
        except jwt.PyJWTError as exc:
            raise InvalidTokenError(str(exc)) from exc
        return claims


def extract_acessos(claims: dict[str, Any]) -> dict[str, list[str]]:
    """Le app_metadata.acessos do payload do JWT.

    O hook do README (secao 7.3) sempre popula isso via `coalesce(..., '{}')`,
    mas um token vindo de outro fluxo pode nao ter `app_metadata`/`acessos` -
    trata a ausencia como {} em vez de deixar um KeyError estourar.
    """
    app_metadata = claims.get("app_metadata") or {}
    return app_metadata.get("acessos") or {}


def extract_nome(claims: dict[str, Any]) -> str | None:
    """Le user_metadata.nome do payload do JWT - o GoTrue espelha
    auth.users.raw_user_meta_data ali automaticamente, sem precisar do hook
    de app_metadata.acessos. Populado quando o admin informa `nome` ao criar
    o usuario (app/supabase_admin_client.py); ausente para usuarios antigos
    ou criados sem nome."""
    user_metadata = claims.get("user_metadata") or {}
    nome = user_metadata.get("nome")
    return nome if isinstance(nome, str) and nome.strip() else None


def usuario_atual_via_header(
    request: Request, authorization: str = Header(...)
) -> dict[str, Any]:
    """Dependencia de referencia para APPS CLIENTES (nao o portal).

    E assim que uma aplicacao cliente deve validar, por conta propria, o
    token recebido do portal via POST /token - usando so a chave publica do
    Supabase (JWKS), sem confiar na palavra do portal. O portal valida a
    PROPRIA sessao de outro jeito (cookie assinado, ver app/deps.py).
    """
    verifier: JWKSVerifier = request.app.state.jwks_verifier
    token = authorization.removeprefix("Bearer ").strip()
    try:
        claims = verifier.verify(token)
    except InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail="token invalido") from exc
    return {
        "id": claims["sub"],
        "email": claims.get("email"),
        "acessos": extract_acessos(claims),
    }
