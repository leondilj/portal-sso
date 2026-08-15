# Lab Supabase Self-Hosted + Portal SSO

Documentação do ambiente montado: VM Linux no VirtualBox rodando Supabase self-hosted, DNS local, reverse proxy e base de um portal SSO corporativo.

**Ambiente final**

- Host: Windows 11
- VM: Ubuntu Server 24.04 LTS (VirtualBox), IP fixo `192.168.0.15`
- Supabase self-hosted `v0.7.2` (Docker)
- DNS local: dnsmasq (`*.lab.internal`)
- Reverse proxy: Caddy
- Usuário da VM: `supabase` / hostname `supabase-linux`

---

## 1. Virtualização

### 1.1 Pré-requisito crítico: desabilitar Hyper-V

O Hyper-V/WSL2 do Windows retém o VT-x e força o VirtualBox a um backend emulado. Sintoma: kernel panic no boot do Ubuntu (`rcu_preempt detected stalls`, `NMIs are not reaching exc_nmi()`) e ícone de tartaruga na barra da VM.

No **cmd como administrador** (o PowerShell da máquina estava com PATH quebrado):

```cmd
bcdedit.exe /set hypervisorlaunchtype off
```

Reiniciar o Windows. Para reverter: `bcdedit /set hypervisorlaunchtype auto`.

> Isso desativa WSL2, Docker Desktop, Hyper-V e Windows Sandbox enquanto estiver ativo.

### 1.2 Criação da VM

| Parâmetro | Valor |
|---|---|
| Nome | `supabase-linux` |
| ISO | `ubuntu-24.04.4-live-server-amd64.iso` |
| Unattended Install | **Skip** (obrigatório) |
| CPUs / RAM | 4 / 8192 MB |
| Disco | 60 GB dinâmico |
| Rede | Bridged Adapter → placa física real |
| Adapter Type | Intel PRO/1000 MT Desktop (82540EM) |
| Promiscuous Mode | Allow All |

**Por que "Skip Unattended Installation":** o modo desassistido não instala o OpenSSH server e não permite ajustar o particionamento.

### 1.3 Instalação do Ubuntu

Pontos que exigem atenção:

- **Storage:** o instalador aloca por padrão só metade do disco à raiz com LVM. Editar `ubuntu-lv` → Size para o máximo (`57.99G`), senão sobra 29 GB não alocados — insuficiente para as 13 imagens Docker + dados.
- **SSH Setup:** marcar **Install OpenSSH server** com a barra de espaço.
- **Featured snaps:** não marcar nada.
- **Ubuntu Pro:** Skip for now.
- Não fechar a janela nem salvar o estado da VM antes do `Reboot Now` — interromper o instalador corrompe a instalação.

---

## 2. Rede da VM

### 2.1 IP estático (netplan)

DHCP causa duas falhas: o `.env` do Supabase e o dnsmasq apontam para um IP que muda, e o dnsmasq falha no boot por race condition (tenta bind antes do DHCP atribuir o endereço).

`/etc/netplan/50-cloud-init.yaml`:

```yaml
network:
  version: 2
  ethernets:
    enp0s3:
      dhcp4: false
      addresses: [192.168.0.15/24]
      routes:
        - to: default
          via: 192.168.0.1
      nameservers:
        addresses: [127.0.0.1]
```

```bash
sudo netplan apply
```

Remover arquivos concorrentes (`99-dns-override.yaml` com `dhcp4-overrides` era resíduo de tentativa anterior):

```bash
sudo mv /etc/netplan/99-dns-override.yaml /etc/netplan/99-dns-override.yaml.bak
```

**Validação:** `ip a | grep 'inet '` deve mostrar o IP **sem** a palavra `dynamic`.

### 2.2 Acesso por SSH

Do Git Bash no Windows (o PowerShell estava com PATH quebrado, sem reconhecer `ssh`):

```bash
ssh supabase@192.168.0.15
```

### 2.3 VS Code Remote-SSH (edição visual)

O `.env` do Supabase tem dezenas de variáveis e é editado a cada ajuste de configuração. Fazer isso pelo `nano` no terminal funciona, mas o Remote-SSH resolve melhor: a árvore de arquivos da VM abre no VS Code do Windows, com syntax highlight, busca e terminal integrado — e é o mesmo ambiente onde o código Python do portal vai ser escrito.

**Instalar a extensão**

No VS Code: `Ctrl+Shift+X` → buscar **Remote - SSH** (Microsoft) → Install.

**Configurar o host**

`F1` → *Remote-SSH: Open SSH Configuration File* → escolher `C:\Users\<user>\.ssh\config`:

```
Host supabase-lab
    HostName 192.168.0.15
    User supabase
    ForwardAgent yes
```

**Conectar**

`F1` → *Remote-SSH: Connect to Host* → `supabase-lab`. Na primeira vez o VS Code instala o servidor dele na VM (leva ~1 min) e pede a senha.

**Abrir o projeto**

*File → Open Folder* → `/home/supabase/supabase-project` → o `.env` fica a um clique na árvore lateral.

**Autenticação por chave (opcional, dispensa senha a cada conexão)**

No Git Bash do Windows:

```bash
ssh-keygen -t ed25519 -C "vscode-lab"
ssh-copy-id supabase@192.168.0.15
```

Se `ssh-copy-id` não existir no Git Bash:

```bash
cat ~/.ssh/id_ed25519.pub | ssh supabase@192.168.0.15 "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 700 ~/.ssh && chmod 600 ~/.ssh/authorized_keys"
```

**Vantagens sobre editar via `scp`**

Baixar o `.env`, editar no Bloco de Notas e devolver introduz quebras de linha CRLF, que quebram a leitura das variáveis pelos containers. O Remote-SSH edita o arquivo no lugar, mantendo LF.

> A extensão **PostgreSQL** instalada nesse contexto roda *dentro* da VM: conecta em `localhost:5432` sem túnel SSH e sem expor a porta do Postgres na rede (ver seção 10).

---

## 3. Supabase self-hosted

### 3.1 Instalação

```bash
sudo apt update && sudo apt upgrade -y
curl -fsSL https://supabase.link/setup.sh | sh
```

URLs informadas ao script:

```
SUPABASE_PUBLIC_URL  = http://192.168.0.15:8000
API_EXTERNAL_URL     = http://192.168.0.15:8000/auth/v1
SITE_URL             = http://192.168.0.15:3000
```

**Falha ocorrida:** o script abortou em `docker is installed but the daemon is not running`, antes de gerar as chaves assimétricas e diversas variáveis do `.env`. Isso gerou uma cadeia de correções manuais (seções 6 e 7).

Correção:

```bash
sudo systemctl start docker
sudo usermod -aG docker $USER
exit   # reconectar para o grupo valer
```

Retomar:

```bash
cd supabase-project
sh utils/add-new-auth-keys.sh
sh run.sh start
```

### 3.2 Comandos do run.sh

```bash
sh run.sh start              # sobe a stack
sh run.sh stop               # para
sh run.sh restart            # reinicia processos (NÃO recarrega .env)
sh run.sh recreate           # recria containers com o .env atual
sh run.sh recreate auth      # recria um serviço específico
sh run.sh logs auth -f       # segue log de um serviço
sh run.sh secrets            # imprime credenciais
sh run.sh printenv auth      # variáveis efetivas no container
sh run.sh update             # atualiza imagens
sh reset.sh                  # APAGA TUDO e regenera secrets
```

> `restart` não recarrega variáveis de ambiente. Toda alteração no `.env` exige `recreate`.

---

## 4. DNS local (dnsmasq)

### 4.1 Liberar a porta 53

```bash
sudo mkdir -p /etc/systemd/resolved.conf.d
sudo tee /etc/systemd/resolved.conf.d/no-stub.conf > /dev/null <<'EOF'
[Resolve]
DNSStubListener=no
EOF
sudo ln -sf /run/systemd/resolve/resolv.conf /etc/resolv.conf
sudo systemctl restart systemd-resolved
```

### 4.2 Configuração

```bash
sudo apt install -y dnsmasq
sudo nano /etc/dnsmasq.d/lab.conf
```

```
interface=lo
interface=enp0s3
except-interface=docker0
bind-interfaces
domain-needed
bogus-priv
no-resolv
server=1.1.1.1
server=8.8.8.8
address=/lab.internal/192.168.0.15
```

```bash
sudo systemctl enable --now dnsmasq
sudo ufw allow 53
```

> **Usar `interface=` e não `listen-address=`.** Com `listen-address=192.168.0.15` o serviço falha no boot (`failed to create listening socket: Cannot assign requested address`) porque tenta bind antes do IP existir.

`address=/lab.internal/IP` é curinga — resolve qualquer subdomínio sem cadastro individual.

Não usar `.local` (colide com mDNS). `.internal` é reservado pela ICANN para uso privado.

### 4.3 Apontar o Windows

PowerShell **como administrador**:

```powershell
Get-NetAdapter
Set-DnsClientServerAddress -InterfaceAlias "Wi-Fi" -ServerAddresses 192.168.0.15
Disable-NetAdapterBinding -Name "Wi-Fi" -ComponentID ms_tcpip6
ipconfig /flushdns
nslookup supabase.lab.internal
```

**Desabilitar IPv6 é obrigatório neste ambiente:** o Windows continuava preferindo o DNS IPv6 da operadora (Virtua) mesmo após configurar o IPv4.

Não adicionar DNS secundário público — o Windows alterna entre os dois e a resolução de `.lab.internal` falha intermitentemente. O dnsmasq já encaminha para 1.1.1.1.

Reverter: `Set-DnsClientServerAddress -InterfaceAlias "Wi-Fi" -ResetServerAddresses`

> Essa configuração se perde quando a placa reconecta ou o Windows reinicia. Alternativa de contingência: adicionar as entradas em `C:\Windows\System32\drivers\etc\hosts`.

---

## 5. Reverse proxy (Caddy)

```bash
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update && sudo apt install -y caddy
```

`/etc/caddy/Caddyfile`:

```
http://supabase.lab.internal {
    reverse_proxy localhost:8000
}
http://app.lab.internal {
    reverse_proxy localhost:8080
}
http://portal.lab.internal {
    reverse_proxy localhost:8080
}
```

```bash
sudo systemctl restart caddy
sudo ufw allow 80/tcp
```

> Usar `restart`, não `reload` — `reload` não funciona em serviço nunca iniciado.
>
> HTTP puro por ora. Com `tls internal` seria necessário importar a CA do Caddy nas Autoridades Raiz Confiáveis do Windows.

**502 Bad Gateway** significa DNS + Caddy funcionando, mas nada escutando na porta de destino.

### 5.1 Atualizar o .env para os domínios

```dotenv
SUPABASE_PUBLIC_URL=http://supabase.lab.internal
API_EXTERNAL_URL=http://supabase.lab.internal/auth/v1
SITE_URL=http://app.lab.internal
```

```bash
sh run.sh recreate
```

Obrigatório: o GoTrue monta links de confirmação e redirect a partir dessas variáveis.

---

## 6. Configuração do Auth

O Studio self-hosted **não tem** interface de configuração de Auth — tudo é `.env` + `recreate`.

```dotenv
SITE_URL=http://app.lab.internal
ADDITIONAL_REDIRECT_URLS=http://localhost:3000,http://localhost:8080,http://192.168.0.15:8080
DISABLE_SIGNUP=false
ENABLE_EMAIL_SIGNUP=true
ENABLE_EMAIL_AUTOCONFIRM=true
JWT_EXPIRY=1800
```

`ENABLE_EMAIL_AUTOCONFIRM=true` dispensa SMTP em ambiente de teste.

`JWT_EXPIRY` curto importa: os papéis viajam dentro do token, então uma revogação de acesso só tem efeito após expiração ou refresh.

Verificar o que foi aplicado de fato:

```bash
sh run.sh printenv auth | grep -i -E 'site_url|redirect|autoconfirm|signup|jwt_expiry|hook'
curl -s http://supabase.lab.internal/auth/v1/settings | python3 -m json.tool
```

Referência completa: https://supabase.com/docs/guides/self-hosting/auth/config

Se uma variável da doc não aparecer no `printenv`, ela não está mapeada no `docker-compose.yml` e precisa ser adicionada no bloco `environment:` do serviço.

---

## 7. Modelo de dados do portal SSO

**Princípio:** papel não é atributo do usuário, é atributo da relação usuário × aplicação. João é gerente *na* Qualidade e analista *em* Vendas.

### 7.1 Tabelas

```sql
create table public.aplicacoes (
  id         text primary key,
  nome       text not null,
  descricao  text,
  url        text not null,
  icone      text,
  ativo      boolean not null default true,
  ordem      int not null default 0,
  criado_em  timestamptz not null default now()
);

create table public.papeis (
  id           uuid primary key default gen_random_uuid(),
  aplicacao_id text not null references public.aplicacoes(id) on delete cascade,
  codigo       text not null,
  nome         text not null,
  descricao    text,
  criado_em    timestamptz not null default now(),
  unique (aplicacao_id, codigo)
);

create table public.usuario_papeis (
  user_id       uuid not null references auth.users(id) on delete cascade,
  papel_id      uuid not null references public.papeis(id) on delete cascade,
  concedido_em  timestamptz not null default now(),
  concedido_por uuid references auth.users(id),
  primary key (user_id, papel_id)
);

create index idx_usuario_papeis_user on public.usuario_papeis(user_id);
create index idx_papeis_aplicacao on public.papeis(aplicacao_id);
```

### 7.2 RLS

```sql
alter table public.aplicacoes     enable row level security;
alter table public.papeis         enable row level security;
alter table public.usuario_papeis enable row level security;

create policy "ve proprios papeis" on public.usuario_papeis
  for select to authenticated
  using ( (select auth.uid()) = user_id );

create policy "le aplicacoes" on public.aplicacoes
  for select to authenticated using (true);

create policy "le papeis" on public.papeis
  for select to authenticated using (true);
```

Sem policy de insert/update/delete: concessão de papéis só pelo backend administrativo com `SECRET_KEY` (que ignora RLS). Nenhum usuário pode se auto-conceder acesso.

### 7.3 Custom Access Token Hook

```sql
create or replace function public.custom_access_token_hook(event jsonb)
returns jsonb
language plpgsql
stable
as $$
declare
  claims  jsonb;
  acessos jsonb;
begin
  select coalesce(jsonb_object_agg(t.aplicacao_id, t.codigos), '{}'::jsonb)
    into acessos
  from (
    select pa.aplicacao_id, jsonb_agg(pa.codigo order by pa.codigo) as codigos
    from public.usuario_papeis up
    join public.papeis pa on pa.id = up.papel_id
    join public.aplicacoes a on a.id = pa.aplicacao_id and a.ativo
    where up.user_id = (event->>'user_id')::uuid
    group by pa.aplicacao_id
  ) t;

  claims := coalesce(event->'claims', '{}'::jsonb);
  claims := jsonb_set(claims, '{app_metadata}',
                      coalesce(claims->'app_metadata', '{}'::jsonb));
  claims := jsonb_set(claims, '{app_metadata,acessos}', acessos);

  return jsonb_set(event, '{claims}', claims);
end;
$$;

grant usage on schema public to supabase_auth_admin;
grant execute on function public.custom_access_token_hook(jsonb) to supabase_auth_admin;
revoke execute on function public.custom_access_token_hook(jsonb) from authenticated, anon, public;

grant select on public.usuario_papeis, public.papeis, public.aplicacoes to supabase_auth_admin;

create policy "auth admin le usuario_papeis" on public.usuario_papeis
  as permissive for select to supabase_auth_admin using (true);

create policy "auth admin le papeis" on public.papeis
  as permissive for select to supabase_auth_admin using (true);

create policy "auth admin le aplicacoes" on public.aplicacoes
  as permissive for select to supabase_auth_admin using (true);
```

> As três policies para `supabase_auth_admin` são fáceis de esquecer e o sintoma é silencioso: o hook roda, não dá erro, e retorna `acessos` vazio sempre.

### 7.4 Dados de teste

```sql
insert into public.aplicacoes (id, nome, descricao, url, ordem) values
  ('qualidade', 'Qualidade', 'Controle de qualidade e laudos', 'http://qualidade.lab.internal', 1),
  ('vendas',    'Vendas',    'Pedidos e carteira de clientes', 'http://vendas.lab.internal',    2),
  ('pcp',       'PCP',       'Planejamento e controle',        'http://pcp.lab.internal',       3);

insert into public.papeis (aplicacao_id, codigo, nome) values
  ('qualidade', 'gerente',  'Gerente'),
  ('qualidade', 'analista', 'Analista'),
  ('vendas',    'gerente',  'Gerente'),
  ('vendas',    'analista', 'Analista'),
  ('pcp',       'operador', 'Operador');

insert into public.usuario_papeis (user_id, papel_id)
select u.id, p.id
from auth.users u, public.papeis p
where u.email = 'joao@lab.internal'
  and ( (p.aplicacao_id = 'qualidade' and p.codigo = 'gerente')
     or (p.aplicacao_id = 'vendas'    and p.codigo = 'analista') );
```

### 7.5 Ativar o hook

**Só depois** de a função existir no banco — se ativar antes, todo login falha.

```dotenv
GOTRUE_HOOK_CUSTOM_ACCESS_TOKEN_ENABLED=true
GOTRUE_HOOK_CUSTOM_ACCESS_TOKEN_URI=pg-functions://postgres/public/custom_access_token_hook
```

```bash
sh run.sh recreate auth
```

### 7.6 Validação

Teste isolado da função, sem precisar logar:

```sql
select public.custom_access_token_hook(
  jsonb_build_object(
    'user_id', (select id from auth.users where email = 'joao@lab.internal'),
    'claims',  '{}'::jsonb
  )
);
```

Teste do token real:

```bash
KEY=$(grep '^SUPABASE_PUBLISHABLE_KEY=' .env | cut -d= -f2)
curl -s -X POST 'http://supabase.lab.internal/auth/v1/token?grant_type=password' \
  -H "apikey: $KEY" \
  -H "Content-Type: application/json" \
  -d '{"email":"joao@lab.internal","password":"SENHA"}'
```

**Resultado obtido** (payload decodificado):

```json
{
  "app_metadata": {
    "acessos": { "qualidade": ["gerente"], "vendas": ["analista"] },
    "provider": "email"
  },
  "iss": "http://supabase.lab.internal/auth/v1",
  "role": "authenticated"
}
```

Algoritmo **ES256** com `kid` — chaves assimétricas funcionando, JWKS disponível para as aplicações validarem sem segredo compartilhado.

---

## 8. Arquitetura do portal (mini authorization code flow)

```
1. João → portal → login (Supabase) → sessão no portal
2. Clica em "Qualidade" → portal gera code de uso único → redirect
3. App Qualidade recebe o code → troca no backend (com client_secret)
4. Portal devolve o access_token → app valida via JWKS
```

O token nunca trafega na URL. O code é inútil sem o `client_secret`.

**Chave pública valida, chave privada só o GoTrue tem.** Nenhum segredo compartilhado entre portal e aplicações — se fosse HS256 com secret distribuído, um vazamento em qualquer app permitiria forjar tokens de admin em todas.

### 8.1 Tabelas de suporte

```sql
create table public.app_clients (
  aplicacao_id  text primary key references public.aplicacoes(id) on delete cascade,
  client_secret text not null,
  redirect_uris text[] not null
);

create table public.auth_codes (
  code          text primary key,
  user_id       uuid not null references auth.users(id) on delete cascade,
  aplicacao_id  text not null references public.aplicacoes(id) on delete cascade,
  redirect_uri  text not null,
  access_token  text not null,
  refresh_token text,
  expira_em     timestamptz not null,
  usado_em      timestamptz
);

alter table public.app_clients enable row level security;
alter table public.auth_codes  enable row level security;

insert into public.app_clients values
  ('qualidade', 'segredo-qualidade-trocar', array['http://qualidade.lab.internal/callback']),
  ('vendas',    'segredo-vendas-trocar',    array['http://vendas.lab.internal/callback']);
```

Sem policies: apenas o portal acessa, com `SECRET_KEY`.

### 8.2 Stack Python

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install fastapi "uvicorn[standard]" supabase asyncpg pyjwt itsdangerous jinja2 python-multipart httpx
```

**Decisão de arquitetura:** do backend, falar Postgres direto (asyncpg), não PostgREST. O `supabase-py` fica só para signup/login/refresh (operações que exigem o GoTrue). Usar PostgREST a partir do FastAPI adiciona um hop de rede desnecessário e, como o backend usaria a `SECRET_KEY`, o RLS seria bypassado de qualquer forma.

Validação de JWT local via JWKS, sem roundtrip HTTP por request:

```python
import jwt
from jwt import PyJWKClient
from fastapi import Depends, HTTPException, Header

jwks = PyJWKClient("http://supabase.lab.internal/auth/v1/.well-known/jwks.json")

def usuario_atual(authorization: str = Header(...)):
    token = authorization.removeprefix("Bearer ").strip()
    try:
        key = jwks.get_signing_key_from_jwt(token).key
        claims = jwt.decode(token, key, algorithms=["ES256"], audience="authenticated")
    except jwt.PyJWTError:
        raise HTTPException(401, "token inválido")
    return {"id": claims["sub"], "email": claims.get("email"),
            "acessos": claims["app_metadata"]["acessos"]}
```

### 8.3 Endpoints do portal

| Rota | Função |
|---|---|
| `POST /login` | autentica no Supabase, grava sessão |
| `GET /` | lê `acessos` do token, lista aplicações |
| `GET /authorize?app_id=` | valida acesso, gera code, redireciona |
| `POST /token` | troca code por token (valida `client_secret`) |

Ponto crítico no `/token`: `select ... for update` dentro de transação, marcando `usado_em`. Impede replay em corrida — dois requests simultâneos com o mesmo code, só um passa.

Do lado da aplicação cliente: troca o code no `/callback`, valida a assinatura via JWKS por conta própria (não confia no portal, só na chave pública do Supabase) e monta a sessão interna.

### 8.4 Integração com sistemas legados

Cada sistema existente ganha um adaptador que: busca a chave pública no JWKS, valida a assinatura, e lê `acessos["vendas"]` para montar a sessão interna.

Estratégia Strangler Fig: cada app mantém o login próprio e ganha um botão "Entrar pelo Portal". Migração setor por setor, sem big bang.

### 8.5 Pendências conhecidas

- `client_secret` em texto puro — usar hash (`pgcrypto` / `crypt()`) fora do lab
- Falta limpeza de codes expirados (cron com `delete from auth_codes where expira_em < now() - interval '1 day'`)
- O portal repassa o token do Supabase inteiro — Vendas recebe token que também vale para Qualidade. Em produção, emitir token por audiência
- Token cresce com muitas aplicações; alternativa é levar só `app_id` e cada app consultar seus papéis via RPC

---

## 8.6 Portal SSO — implementação

A arquitetura acima está implementada em [`portal/`](portal/) (FastAPI, seguindo
o stack decidido em 8.2). As migrations SQL do schema (7.1–8.1) estão em
[`sql/`](sql/), separadas do código do portal — são aplicadas direto no
Postgres do Supabase, independente do container do portal estar rodando.

Instruções de configuração, variáveis de ambiente e como rodar (local ou
Docker) estão em [`portal/README.md`](portal/README.md). Escopo desta
primeira versão: login, listagem de aplicações, `GET /authorize` e
`POST /token`.

O lado "aplicação cliente" desse fluxo está demonstrado em
[`qualidade/`](qualidade/): recebe o `code`, troca por token no portal,
valida a assinatura via JWKS por conta própria (sem confiar no portal) e
mostra o papel do usuário especificamente em Qualidade. Detalhes em
[`qualidade/README.md`](qualidade/README.md) — inclui o bloco de Caddy que
ainda falta adicionar na VM do lab para `qualidade.lab.internal`.

---

## 9. MCP do Supabase

Dá ao agente (Claude Code) acesso ao schema real: ler tabelas, rodar SQL, aplicar migrations. Não gera código — quem gera é o agente; o MCP evita que ele chute nomes de tabela.

### 9.1 Liberar no Kong

Bloqueado por padrão. Descobrir o gateway da rede Docker:

```bash
docker inspect supabase-kong --format '{{range .NetworkSettings.Networks}}{{println .Gateway}}{{end}}'
# → 172.18.0.1
```

Em `volumes/api/kong.yml`, seção `- name: mcp` (rota para `http://studio:3000/api/mcp`):

```yaml
    plugins:
      # Block access to /mcp by default
      #- name: request-termination
      #  config:
      #    status_code: 403
      #    message: "Access is forbidden."
      - name: cors
      - name: ip-restriction
        config:
          allow:
            - 127.0.0.1
            - ::1
            - 172.18.0.1
          deny: []
```

Comentar **todas** as linhas do `request-termination`, incluindo o `config:`. Não esquecer o `deny: []` — o plugin exige as duas listas.

```bash
sh run.sh recreate kong
```

### 9.2 Correção: supabase_read_only_user

Decorrência do `setup.sh` interrompido. O `docker-compose.yml` declarava apenas `POSTGRES_USER_READ_WRITE`, sem a variante read-only.

No `docker-compose.yml`, serviço `studio`, abaixo de `POSTGRES_USER_READ_WRITE`:

```yaml
      POSTGRES_USER_READ_ONLY: supabase_read_only_user
      POSTGRES_PASSWORD_READ_ONLY: ${POSTGRES_READ_ONLY_PASSWORD}
```

No `.env`:

```dotenv
POSTGRES_READ_ONLY_PASSWORD=<senha>
```

O role existia mas **sem atributo LOGIN**, e alterá-lo é barrado por event trigger do Supabase mesmo sendo superuser. Contornar com `session_replication_role`:

```bash
docker compose exec db psql -U supabase_admin -d postgres -c \
  "set session_replication_role = replica; alter role supabase_read_only_user with login password '<senha>';"
```

Validar:

```bash
docker compose exec db psql "postgresql://supabase_read_only_user:<senha>@localhost:5432/postgres" -c "select current_user;"
```

> `docker compose exec` com heredoc exige `-T` (`cannot attach stdin to a TTY-enabled container`).
>
> `psql -U postgres` na imagem do Supabase **não** é superuser real — usar `supabase_admin`.

**Guardar o compose editado**, pois `sh run.sh update` sobrescreve:

```bash
cp docker-compose.yml docker-compose.yml.bak-custom
```

### 9.3 Conectar o Claude Code

Rodando **dentro da VM** (sem túnel):

```bash
claude mcp add supabase --transport http http://localhost:8000/mcp
claude mcp list
```

No Windows, exigiria túnel SSH — mas atenção: `ssh -L 8000:localhost:8000` **executado a partir da VM** cria listener na 8000 dentro dela e colide com o Kong (`address already in use`).

### 9.4 Teste direto

```bash
curl -s -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

Tools disponíveis: `search_docs`, `list_tables`, `list_extensions`, `list_migrations`, `apply_migration`, `execute_sql`, `get_logs`, `get_advisors`, `get_project_url`, `get_publishable_keys`, `generate_typescript_types`.

**Status:** `tools/list` responde; `tools/call` ainda retorna `password authentication failed for user "supabase_read_only_user"` mesmo com a conexão direta ao banco funcionando. Pendente de investigação.

> Manter aprovação manual em `apply_migration`. Conteúdo do banco entra no contexto do agente — superfície a considerar ao popular com dados de terceiros.

---

## 10. Acesso ao banco por cliente SQL

O Postgres escuta apenas em `127.0.0.1` dentro da VM.

### Opção A — Túnel SSH (do Windows)

```bash
ssh -L 5433:localhost:5432 supabase@192.168.0.15
```

| Campo | Valor |
|---|---|
| Host | `localhost` |
| Porta | `5433` |
| Database | `postgres` |
| User | `postgres` |
| Password | valor de `POSTGRES_PASSWORD` no `.env` |

### Opção B — VS Code Remote-SSH (recomendada)

Com o Remote-SSH já configurado (seção 2.3), instalar a extensão **PostgreSQL** *no contexto remoto* — o VS Code oferece um botão "Install in SSH: supabase-lab" para isso.

O cliente SQL passa a rodar dentro da VM: conecta em `localhost:5432` sem túnel e sem expor porta na rede.

| Campo | Valor |
|---|---|
| Host | `localhost` |
| Porta | `5432` |
| Database | `postgres` |
| User | `postgres` |
| Password | valor de `POSTGRES_PASSWORD` no `.env` |

### Opção C — Expor a porta

Remover o prefixo `127.0.0.1:` do mapeamento do serviço `db` no compose. Mais cômodo, mas expõe o banco a toda a rede Wi-Fi.

---

## 11. Operação

### Ligar a VM sem interface

```bash
alias vbm='"/c/Program Files/Oracle/VirtualBox/VBoxManage.exe"'
vbm startvm supabase-linux --type headless
vbm list runningvms
vbm controlvm supabase-linux acpipowerbutton
```

### Verificar se subiu

```bash
ping -c 3 192.168.0.15
until ssh -o ConnectTimeout=2 supabase@192.168.0.15 'echo VM pronta'; do sleep 3; done
```

### Mover a VM de diretório

Nunca arrastar o `.vdi` pelo Explorer — o caminho está registrado no `.vbox`. Usar: clique direito na VM → **Mover**. Ou `VBoxManage modifymedium disk <origem> --move <destino>`.

### Checklist pós-boot

```bash
dig +short supabase.lab.internal @127.0.0.1
sudo systemctl status dnsmasq --no-pager | head -3
docker compose ps
```

---

## 12. Armadilhas encontradas

| Sintoma | Causa | Correção |
|---|---|---|
| Kernel panic no boot da VM | Hyper-V retendo VT-x | `bcdedit /set hypervisorlaunchtype off` |
| `Network is unreachable` na instalação | Bridge sobre Wi-Fi bloqueado pelo driver | Promiscuous Mode: Allow All, ou NAT |
| Instalação corrompida | "Salvar estado da VM" durante o instalador | Reinstalar; usar ACPI Shutdown |
| Sem SSH após instalar | Modo unattended do VirtualBox | Skip Unattended; marcar OpenSSH |
| `/` com metade do disco | Default do LVM reserva espaço | Editar `ubuntu-lv` no instalador |
| dnsmasq falha no boot | `listen-address` com IP ainda inexistente | Usar `interface=` |
| DNS do Windows volta à operadora | DHCP reescreve na reconexão | Reaplicar; ou usar `hosts` |
| `.lab.internal` não resolve mesmo com DNS certo | Windows prefere DNS IPv6 da operadora | `Disable-NetAdapterBinding ... ms_tcpip6` |
| `setup.sh` aborta | Docker daemon parado | `systemctl start docker` + `usermod -aG docker` |
| Variáveis do `.env` não aplicam | `restart` não recarrega env | `sh run.sh recreate` |
| Hook retorna `acessos` vazio | Falta policy/grant para `supabase_auth_admin` | Ver 7.3 |
| `address already in use` na 8000 | Túnel SSH aberto de dentro da VM | `kill <pid>` |
| `~cd`, `^[[200~` grudados nos comandos | Bracketed paste do Git Bash | Colar uma linha por vez |
| `ssh`/`bcdedit` não reconhecidos | PATH do PowerShell corrompido | Caminho completo, ou Git Bash/cmd |
| `psql` na porta 5432 do host dá `no tenant identifier provided (ENOIDENTIFIER)` | A porta publicada é o Supavisor (pooler), não o Postgres puro | `docker exec -i supabase-db psql -U supabase_admin -d postgres` direto no container, ou conectar o container cliente à rede Docker do Supabase e falar com `db:5432` |
| Container do portal/Qualidade não resolve `*.lab.internal` | dnsmasq configurado com `except-interface=docker0` (seção 4.2) — o gateway da bridge do Docker não é atendido | Apontar o DNS do container para o IP real da VM (`dns:` no `docker-compose.yml`, não `127.0.0.1` nem o gateway do docker0) |

---

## 13. Estado atual

**Funcionando**

- VM Ubuntu 24.04 LTS, IP fixo, SSH
- Supabase self-hosted com 13 containers
- dnsmasq resolvendo `*.lab.internal` (curinga)
- Caddy roteando por hostname
- Modelo de papéis por aplicação
- Custom Access Token Hook injetando `acessos` no JWT
- Chaves assimétricas ES256 + JWKS
- Login validado com token contendo os papéis corretos
- Portal FastAPI implementado (`portal/`): login, listagem de aplicações,
  `GET /authorize`, `POST /token` — suíte de testes (mocks/fakes, sem
  Supabase/Postgres/Docker reais no ambiente de desenvolvimento) passando
- Migrations SQL do schema do portal prontas em `sql/` (aplicações/papéis,
  hook, `app_clients`/`auth_codes`)
- Aplicação cliente de exemplo implementada (`qualidade/`): troca o code no
  `/callback`, valida o JWT via JWKS por conta própria, mostra o papel do
  usuário em Qualidade e uma área restrita a `gerente` — suíte de testes
  (mocks/fakes) passando

**Pendente**

- MCP: `tools/call` com erro de autenticação do `supabase_read_only_user`
- Aplicar as migrations de `sql/` e validar o Portal FastAPI + a app
  Qualidade de ponta a ponta contra o Supabase real da VM do lab (login,
  hook, `/authorize` → `/token` → `/callback`)
- Adicionar o bloco de Caddy para `qualidade.lab.internal` na VM do lab
  (documentado em `qualidade/README.md`, ainda não aplicado)
- Storage marcado `unhealthy` pelo healthcheck (serviço sobe normalmente)

**Higiene antes de sair do lab**

- Trocar `client_secret` placeholders
- Trocar senha do usuário de teste
- Endurecer `PASSWORD_MIN_LENGTH` / `PASSWORD_REQUIRED_CHARACTERS`
- Rotacionar secrets expostos durante o setup

---

## Referências

- Self-hosting Docker — https://supabase.com/docs/guides/self-hosting/docker
- Auth config — https://supabase.com/docs/guides/self-hosting/auth/config
- Custom Access Token Hook — https://supabase.com/docs/guides/auth/auth-hooks/custom-access-token-hook
- Caddy (Debian/Ubuntu) — https://caddyserver.com/docs/install#debian-ubuntu-raspbian
- supabase-py — https://supabase.com/docs/reference/python/introduction
