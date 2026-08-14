from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

SESSION_COOKIE_NAME = "qualidade_session"
_SALT = "qualidade-session"


@dataclass
class SessionData:
    user_id: str
    email: str | None
    papeis: list[str]


class SessionManager:
    """Cookie de sessao PROPRIO desta app - independente do cookie de sessao
    do portal (secret e nome de cookie diferentes). Depois de validar o
    token na troca do code, esta app nao precisa mais guardar o
    access_token/refresh_token do Supabase: so os papeis ja extraidos, para
    montar a UI."""

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
