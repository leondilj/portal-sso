from __future__ import annotations

from typing import Any

import jwt
from jwt import PyJWKClient


class InvalidTokenError(Exception):
    pass


class JWKSVerifier:
    """Valida localmente, via JWKS, o token que o portal devolveu na troca do
    code. Esta app NAO confia na palavra do portal - verifica a assinatura
    ES256 por conta propria contra a chave publica do Supabase, do mesmo
    jeito que o modulo equivalente em portal/app/jwt_verify.py.

    Duplicado de proposito (nao importado do pacote do portal): um sistema
    legado real, integrando via a estrategia Strangler Fig do README secao
    8.4, nao teria acesso ao codigo Python do portal - so a URL publica do
    JWKS.
    """

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


def extract_papeis(claims: dict[str, Any], aplicacao_id: str = "qualidade") -> list[str]:
    """Le os papeis desta aplicacao especifica de app_metadata.acessos.

    Papel nao e atributo do usuario, e atributo da relacao usuario x
    aplicacao (README secao 7) - por isso so lemos `acessos[aplicacao_id]`,
    nao o mapa inteiro.
    """
    app_metadata = claims.get("app_metadata") or {}
    acessos = app_metadata.get("acessos") or {}
    return acessos.get(aplicacao_id) or []
