# Portal SSO

Aplicacao FastAPI que implementa o mini authorization code flow descrito na
secao 8 do [README.md da raiz](../README.md): login central via Supabase,
listagem das aplicacoes que o usuario pode acessar (a partir de `acessos` no
JWT), emissao de `code` de uso unico via `GET /authorize` e troca desse code
por um token via `POST /token`.

Este diretorio contem so o portal em si. As migrations do schema
compartilhado (tabelas de aplicacoes/papeis, o Custom Access Token Hook,
`app_clients`/`auth_codes`) ficam em [`../sql/`](../sql/) e sao aplicadas
direto no Postgres do Supabase (via psql, Studio ou o MCP `apply_migration`),
independente deste app estar rodando.

## Como isso se encaixa no lab

1. Aplique as migrations de `../sql/` no Supabase (nessa ordem: `0001`,
   `0002`, `0003`, e opcionalmente `0004` so em dev/lab).
2. **So depois** de `0002_access_token_hook.sql` ter sido aplicada, ative o
   hook no `.env` do Supabase (README raiz, secao 7.5) e rode
   `sh run.sh recreate auth`. Ativar antes da funcao existir derruba todo
   login.
3. Suba o portal (local ou Docker, ver abaixo) apontando para o Supabase do
   lab via `.env`.
4. O Caddy do lab ja roteia `portal.lab.internal` -> `localhost:8080`
   (README raiz, secao 5) - o portal escuta em `0.0.0.0:8080` por padrao.

## Rodando localmente

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

cp .env.example .env
# edite .env com a URL/chaves do seu Supabase e um DATABASE_URL valido

uvicorn app.main:app --reload --port 8080
```

## Rodando em Docker

```bash
cp .env.example .env
# edite .env

docker compose up --build
```

## Variaveis de ambiente

| Variavel | Para que serve |
|---|---|
| `SUPABASE_URL` | Base URL do GoTrue, usada pelo `supabase-py` no login/refresh (mesmo valor de `SUPABASE_PUBLIC_URL` no `.env` do Supabase) |
| `SUPABASE_PUBLISHABLE_KEY` | Chave publica/anon do Supabase |
| `SUPABASE_JWKS_URL` | Endpoint JWKS para validar o JWT localmente (ES256), sem round-trip por request |
| `PORTAL_DATABASE_URL` | DSN Postgres (asyncpg) com uma role privilegiada, para acesso direto as tabelas do portal - **nao e a mesma coisa** que a `SECRET_KEY`/service-role do Supabase, que so vale para chamadas HTTP via PostgREST/GoTrue. Aponte para `db` (o container, via `SUPABASE_DOCKER_NETWORK` abaixo), nao para a porta 5432 publicada no host - em instalacoes self-hosted recentes essa porta fica atras do Supavisor (pooler), que exige um identificador de tenant e rejeita uma conexao comum |
| `SUPABASE_DOCKER_NETWORK` | Nome da rede Docker da stack do Supabase (`docker network ls` no host) - o `docker-compose.yml` do portal entra nessa rede para o container falar direto com `db:5432` |
| `PORTAL_DNS_SERVER` | IP real da VM (nao 127.0.0.1) onde o dnsmasq do lab escuta - necessario porque o dnsmasq costuma estar configurado com `except-interface=docker0` (README raiz, secao 4.2), entao o gateway da bridge do Docker nao resolve `*.lab.internal` de dentro do container |
| `PORTAL_SESSION_SECRET` | Chave de assinatura do cookie de sessao (itsdangerous) |
| `PORTAL_SESSION_MAX_AGE_SECONDS` | Validade do cookie de sessao - alinhe com `JWT_EXPIRY` do Supabase |
| `PORTAL_COOKIE_SECURE` | `true` so se o portal estiver atras de TLS |
| `PORTAL_AUTH_CODE_TTL_SECONDS` | Validade de um `code` emitido por `/authorize` ate ser trocado em `/token` |
| `PORTAL_HOST` / `PORTAL_PORT` | Bind do servidor (o Dockerfile fixa `0.0.0.0:8080` no `CMD`, consistente com o Caddy do lab) |

## Rodando os testes

```bash
pip install -e ".[dev]"
pytest
ruff check .
mypy app
```

Nao ha Supabase, Postgres nem Docker reais disponiveis no ambiente onde este
app foi desenvolvido - a suite inteira roda contra fakes/mocks: um par de
chaves ES256 gerado no proprio teste (`tests/conftest.py`) no lugar do JWKS
real, e um "fake pool" em memoria no lugar do asyncpg, que emula o
`select ... for update` do Postgres com um lock para provar a protecao
contra replay em `/token`. Isso cobre a logica da aplicacao, mas **nao**
prova: o formato real da resposta do GoTrue, o comportamento real do wire
protocol do asyncpg, nem concorrencia real de linha do Postgres sob carga.
Validar isso de verdade exige rodar contra o Supabase da VM do lab.

## Limitacoes conhecidas (nao resolvidas nesta versao)

- O portal repassa ao app cliente o token inteiro do Supabase, sem escopo
  por audiencia - um app recebe um token que tambem vale para os outros.
- `client_secret` fica em texto puro em `app_clients` (usar `pgcrypto`/
  `crypt()` fora do lab).
- Nao ha job de limpeza para `auth_codes` expirados (um
  `delete from auth_codes where expira_em < now() - interval '1 day'`
  periodico resolveria).
- Sem refresh automatico de sessao: quando o cookie expira, o usuario e
  mandado de volta para `/login`.
- `GET /authorize` sempre usa o primeiro `redirect_uri` cadastrado para a
  aplicacao (sem selecao por parametro).

Uma aplicacao cliente de exemplo (Qualidade), demonstrando o outro lado
deste fluxo, esta em [`../qualidade/`](../qualidade/).
