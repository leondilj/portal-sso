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


# --- Area administrativa (app/db_admin.py, app/routers/admin/) ---


class AplicacaoRow(BaseModel):
    id: str
    nome: str
    descricao: str | None = None
    url: str
    icone: str | None = None
    ativo: bool
    ordem: int
    criado_em: datetime


class PapelRow(BaseModel):
    id: str
    aplicacao_id: str
    codigo: str
    nome: str
    descricao: str | None = None
    criado_em: datetime


class PapelComAplicacaoRow(PapelRow):
    aplicacao_nome: str


class AppClientSummary(BaseModel):
    """Resumo de app_clients SEM o client_secret - usado em toda leitura
    administrativa fora da revelacao unica logo apos criar/regenerar. O
    secret nunca entra na memoria de um request que so precisa mostrar se
    o app ja esta configurado como cliente OAuth."""

    aplicacao_id: str
    redirect_uris: list[str]
    has_secret: bool


class AuthUserRow(BaseModel):
    id: str
    email: str | None
    nome: str | None = None
    created_at: datetime
    last_sign_in_at: datetime | None
    email_confirmed_at: datetime | None


class UsuarioPapelRow(BaseModel):
    papel_id: str
    aplicacao_id: str
    aplicacao_nome: str
    codigo: str
    nome: str
    concedido_em: datetime


class PapelConcedidoResumo(BaseModel):
    papel_id: str
    codigo: str
    nome: str


class UsuarioDoSistemaRow(BaseModel):
    id: str
    email: str | None
    nome: str | None = None
    papeis: list[PapelConcedidoResumo]
