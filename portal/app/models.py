from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class AppTile(BaseModel):
    id: str
    nome: str
    descricao: str | None = None
    url: str
    icone: str | None = None


class AppClient(BaseModel):
    aplicacao_id: str
    client_secret: str
    redirect_uris: list[str]


class AuthCodeRow(BaseModel):
    code: str
    user_id: str
    aplicacao_id: str
    redirect_uri: str
    access_token: str
    refresh_token: str | None
    expira_em: datetime
    usado_em: datetime | None


class TokenRequest(BaseModel):
    code: str
    client_secret: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str | None = None


class TokenErrorResponse(BaseModel):
    error: str
