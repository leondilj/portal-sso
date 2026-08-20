from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

SESSION_COOKIE_NAME = "portal_session"
_SALT = "portal-session"

FLASH_SECRET_COOKIE_NAME = "portal_flash_secret"
_FLASH_SALT = "portal-flash-secret"


@dataclass
class SessionData:
    user_id: str
    email: str | None
    access_token: str
    refresh_token: str | None
    acessos: dict[str, list[str]]
    nome: str | None = None


class SessionManager:
    """Cookie de sessao assinado (nao criptografado) via itsdangerous.

    Guarda o token de acesso do Supabase e os `acessos` ja extraidos, para
    que GET / e GET /authorize nao precisem redecodificar o JWT a cada
    request. Sem refresh automatico nesta versao: quando o cookie expira
    (alinhado a JWT_EXPIRY do Supabase), o usuario e mandado de volta para
    /login.
    """

    def __init__(self, secret: str, max_age_seconds: int) -> None:
        self._serializer = URLSafeTimedSerializer(secret, salt=_SALT)
        self._max_age = max_age_seconds

    def encode(self, session: SessionData) -> str:
        return self._serializer.dumps(asdict(session))

    def decode(self, cookie_value: str) -> SessionData | None:
        try:
            payload: Any = self._serializer.loads(cookie_value, max_age=self._max_age)
        except (BadSignature, SignatureExpired):
            return None
        return SessionData(**payload)


class OneTimeSecretCookie:
    """Cookie assinado de vida curta (~5min) para revelar um segredo
    (client_secret novo/regenerado, senha inicial de usuario) exatamente
    uma vez, via POST-redirect-GET: o handler que gera o segredo grava esse
    cookie e redireciona para uma rota GET de revelacao; essa rota decodifica
    o valor e o router chama `response.delete_cookie(FLASH_SECRET_COOKIE_NAME)`
    na MESMA resposta - um refresh ou voltar/avancar no navegador nunca
    mostra o valor de novo, porque a garantia vem do ciclo de vida do
    cookie, nao de o template "so imprimir uma vez".
    """

    def __init__(self, secret: str, max_age_seconds: int = 300) -> None:
        self._serializer = URLSafeTimedSerializer(secret, salt=_FLASH_SALT)
        self._max_age = max_age_seconds

    def encode(self, payload: dict[str, str]) -> str:
        return self._serializer.dumps(payload)

    def decode(self, cookie_value: str) -> dict[str, str] | None:
        try:
            payload: Any = self._serializer.loads(cookie_value, max_age=self._max_age)
        except (BadSignature, SignatureExpired):
            return None
        return payload
