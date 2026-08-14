from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

SESSION_COOKIE_NAME = "portal_session"
_SALT = "portal-session"


@dataclass
class SessionData:
    user_id: str
    email: str | None
    access_token: str
    refresh_token: str | None
    acessos: dict[str, list[str]]


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
