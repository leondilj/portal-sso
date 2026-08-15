# Qualidade — app cliente de exemplo do Portal SSO

App FastAPI mínima que demonstra o lado **aplicação cliente** do mini
authorization code flow descrito na seção 8 do
[README.md da raiz](../README.md): recebe o `code` emitido pelo
`GET /authorize` do [Portal](../portal/), troca esse code por um token no
`POST /token` do portal (server-to-server, com `client_secret`), valida esse
token **por conta própria** via JWKS do Supabase (não confia na palavra do
portal) e monta sua própria sessão, mostrando o papel do usuário
especificamente dentro de Qualidade.

Não tem nenhuma funcionalidade de negócio real — é uma casca mínima para
provar o handshake de SSO e o modelo "papel é atributo da relação usuário ×
aplicação" (README raiz, seção 7) de ponta a ponta. Serve também de
referência para a estratégia Strangler Fig de integração de sistemas
legados (README raiz, seção 8.4): é o adaptador mínimo que qualquer sistema
real ganharia — buscar a chave pública no JWKS, validar a assinatura, ler os
papéis, montar sessão interna.

**Diferença importante em relação ao portal**: esta app não acessa o
Postgres do Supabase em nenhum momento. Tudo que precisa (identidade do
usuário + seus papéis em Qualidade) já vem dentro do JWT recebido na troca
do code. Só faz duas chamadas de rede: `POST` no `/token` do portal, e a
busca da chave pública no JWKS do Supabase.

## Fluxo

1. Usuário clica no tile "Qualidade" no portal.
2. Portal redireciona para `GET /callback?code=...` desta app.
3. Esta app troca o `code` por um token no `POST /token` do portal, usando o
   `client_secret` cadastrado para `qualidade` em `app_clients` (ver
   [`../sql/0003_app_clients_auth_codes.sql`](../sql/0003_app_clients_auth_codes.sql)
   e o seed de dev em
   [`../sql/0004_seed_dev_data.sql`](../sql/0004_seed_dev_data.sql)).
4. Valida o token recebido via JWKS (assinatura ES256, `aud`) — defesa em
   profundidade, não confia cegamente no portal.
5. Lê `acessos["qualidade"]` do JWT (ex.: `["gerente"]`). Se estiver vazio,
   mostra uma página de "sem acesso" em vez de criar sessão.
6. Monta um cookie de sessão **próprio** desta app (independente do cookie
   de sessão do portal) e mostra "Logado como ..., papel em Qualidade:
   ...". Se o papel incluir `gerente`, mostra um link para uma página de
   demonstração (`/area-gerente`) que retorna 403 para quem não é gerente —
   prova visual de que o controle de acesso é por papel.

## Como isso se encaixa no lab

O Caddyfile documentado no README raiz (seção 5) hoje só tem blocos para
`supabase`, `app` e `portal` — falta um bloco para `qualidade.lab.internal`.
Isso é um passo manual na VM do lab (fora deste repositório), igual foi
feito para o portal. Adicione ao `/etc/caddy/Caddyfile`:

```
http://qualidade.lab.internal {
    reverse_proxy localhost:8081
}
```

e rode `sudo systemctl restart caddy`.

## Rodando localmente

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

cp .env.example .env
# edite .env: PORTAL_TOKEN_URL apontando pro portal, QUALIDADE_CLIENT_SECRET
# igual ao cadastrado em app_clients, SUPABASE_JWKS_URL do seu Supabase

uvicorn app.main:app --reload --port 8081
```

## Rodando em Docker

```bash
cp .env.example .env
# edite .env

docker compose up --build
```

## Variáveis de ambiente

| Variável | Para que serve |
|---|---|
| `PORTAL_TOKEN_URL` | URL completa do `POST /token` do portal |
| `QUALIDADE_CLIENT_SECRET` | Tem que bater com `client_secret` cadastrado para `qualidade` em `app_clients` |
| `SUPABASE_JWKS_URL` | Endpoint JWKS para validar o JWT localmente (ES256) |
| `QUALIDADE_SESSION_SECRET` | Chave de assinatura do cookie de sessão desta app (diferente do secret do portal — sessões independentes) |
| `QUALIDADE_SESSION_MAX_AGE_SECONDS` | Validade do cookie de sessão |
| `QUALIDADE_COOKIE_SECURE` | `true` só se estiver atrás de TLS |
| `QUALIDADE_HOST` / `QUALIDADE_PORT` | Bind do servidor (o Dockerfile fixa `0.0.0.0:8081` no `CMD`) |
| `QUALIDADE_DNS_SERVER` | IP real da VM (nao 127.0.0.1) onde o dnsmasq do lab escuta - necessario porque o dnsmasq costuma estar configurado com `except-interface=docker0` (README raiz, secao 4.2), entao o gateway da bridge do Docker nao resolve `*.lab.internal` de dentro do container (precisa para alcancar `PORTAL_TOKEN_URL` e `SUPABASE_JWKS_URL`) |

## Rodando os testes

```bash
pip install -e ".[dev]"
pytest
ruff check .
mypy app
```

Mesma limitação do portal: sem Supabase/portal reais disponíveis no
ambiente onde este app foi desenvolvido, a suíte roda contra fakes/mocks —
um par de chaves ES256 gerado no teste no lugar do JWKS real
(`tests/conftest.py`), e `respx` para simular as respostas do `POST /token`
do portal (`tests/test_portal_client.py`) sem round-trip de rede real. Os
testes de router (`test_callback_router.py`) trocam
`app.state.portal_client.exchange_code` por um stub direto, incluindo um
caso de "defesa em profundidade" onde o portal devolve um token assinado
com outra chave, provando que esta app não aceitaria um token forjado
mesmo se o portal estivesse comprometido. Validar contra o portal e o
Supabase de verdade fica para a VM do lab.

## Limitações conhecidas (mesmas do portal, herdadas do fluxo)

- Nenhuma funcionalidade de negócio real.
- Sem refresh de sessão automático — cookie expirado, precisa passar pelo
  portal de novo.
- `/area-gerente` é só uma página estática de demonstração, não uma
  funcionalidade real.
