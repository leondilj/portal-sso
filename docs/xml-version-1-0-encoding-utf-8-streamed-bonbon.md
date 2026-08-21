# SSO do Portal para a SKP (skpQa) — infra concluída, integração de código

## Contexto

O `portal-sso` deste repositório existe pra centralizar o acesso às aplicações
Kover: hoje cada sistema (incluindo a SKP/`skpQa`) mantém seu próprio contexto
de login e senha, isolado dos demais. A ideia é que o portal vire a porta de
entrada única — quem tem acesso a quê é decidido lá, não em cada app.

A SKP é a primeira aplicação real (fora do exemplo de demonstração
`qualidade/` já existente neste repo) a ser conectada a esse portal. Ela roda
numa máquina Windows na mesma rede da VM do lab (IP `192.168.0.23`), com dois
sites IIS: frontend Vite/JS na porta 5000 (`qaSite`) e API .NET (Minimal API,
`eSKQaWeb.Api`) na porta 8090 (`skpQa`).

Este é um teste/protótipo — ainda nada fechado. A decisão explícita do
usuário foi priorizar o **menor impacto possível** nos projetos client-side
enquanto isso é validado, adiando qualquer mudança estrutural (schema novo,
auto-provisionamento de usuário) pra uma fase futura, quando o impacto nos
demais módulos da SKP (Audit, Inspections, Reports, Segregations) estiver
mais claro.

## Infra (já resolvida e validada nesta sessão — recapitulando, nada a fazer)

- IP fixo `192.168.0.23` (Wi-Fi) — **pendente**: reservar no roteador por MAC,
  hoje é DHCP.
- DNS: wildcard `address=/lab.internal/192.168.0.15` no dnsmasq da VM já
  cobre `skp.ind.lab.internal`, sem mudança necessária.
- Firewall Windows: regras criadas e confirmadas pra `8090` e `5000`,
  restritas à origem `192.168.0.15` (a VM).
- IIS: os dois sites (`skpQa`/8090, `qaSite`/5000) escutando em `0.0.0.0`,
  alcançáveis pela VM (confirmado via `curl` da VM).
- `web.config` do `qaSite` já tem a regra de fallback SPA (`IsFile`/`IsDirectory`
  negate → rewrite pra `/index.html`) — necessária pro `/callback` funcionar
  como full page load vindo do redirect do portal.
- Caddy da VM: bloco final decidido (roteamento por path, um único hostname
  público `skp.ind.lab.internal`):
  ```
  http://skp.ind.lab.internal {
      handle /api/* {
          reverse_proxy 192.168.0.23:8090
      }
      handle {
          reverse_proxy 192.168.0.23:5000
      }
  }
  ```
  **Ação pendente**: aplicar esse bloco no `/etc/caddy/Caddyfile` da VM via
  SSH (substituindo o bloco anterior que apontava só pra 8090) e
  `sudo systemctl restart caddy`.

## Decisão de arquitetura: vínculo de identidade (Opção B — menor impacto)

O login via SSO **não substitui** o modelo de identidade local da SKP — ele é
uma segunda forma de provar quem é, que resolve pro **mesmo usuário local já
cadastrado** em `dbo.Usuario`:

1. Portal autentica o usuário e devolve, no JWT, o e-mail e os papéis em
   `acessos["skp"]`.
2. A API da SKP recebe esse token, valida a assinatura via JWKS (não confia
   cegamente no portal — mesmo princípio do `qualidade/` deste repo), e
   busca o usuário local por e-mail em `dbo.Usuario`.
3. Se achar: monta a mesma `LoginResponse(Token, AuthUserDto, ExpiresAt)` que
   o login local já produz hoje, usando o `Usuario.Id`/`PerfilDescricao`
   **locais** (não o que veio do portal) — `Audit`/`Inspections`/`Reports`
   continuam vendo o mesmo `Usuario.Id` de sempre, sem nenhuma mudança.
4. Se não achar: nega o acesso com mensagem clara ("usuário não cadastrado
   no SKP — contate o administrador"), sem criar nada automaticamente.

Isso significa: **zero schema novo, zero mudança em módulos existentes**,
100% reversível/aditivo (endpoint novo ao lado do `/api/auth/login`
existente). Auto-provisionamento e "portal decide o papel local" ficam para
uma fase 2 deliberada, fora do escopo deste teste.

## 1. Registro da app no portal (`sql/`)

Nova migration `sql/0007_seed_skp.sql`, seguindo exatamente o padrão de
`sql/0004_seed_dev_data.sql` (README seção 7.4/8.1):

```sql
insert into public.aplicacoes (id, nome, descricao, url, ordem) values
  ('skp', 'SKP - Qualidade', 'Sistema Kover de Qualidade', 'http://skp.ind.lab.internal', 4)
on conflict (id) do nothing;

insert into public.papeis (aplicacao_id, codigo, nome) values
  ('skp', 'qualidade',   'Qualidade'),
  ('skp', 'supervisor',  'Supervisor Qualidade'),
  ('skp', 'faturamento', 'Faturamento')
on conflict (aplicacao_id, codigo) do nothing;

insert into public.app_clients (aplicacao_id, client_secret, redirect_uris) values
  ('skp', '<gerar com secrets.token_urlsafe(32) ou equivalente>',
   array['http://skp.ind.lab.internal/callback'])
on conflict (aplicacao_id) do nothing;
```

Códigos de papel (`qualidade`, `supervisor`, `faturamento`) espelham os
perfis já existentes no SKP (`database/manual/010_quality_roles.sql`,
mencionado no comentário de `SkpUserRow`) — mantém o vocabulário consistente
entre portal e app, mesmo que hoje a Opção B não use esse papel do portal
pra decidir nada (o `PerfilDescricao` local é que manda).

Concessão de `usuario_papeis` para os usuários de teste: via SQL manual ou
pela área `/admin` do portal (`POST /admin/sistemas/skp/perfis/novo` já
criando os papéis acima, e concessão de acesso pela tela de usuários).

**Alternativa sem SQL manual**: usar só a área `/admin` do portal
(`POST /admin/sistemas/novo` com `aplicacao_id=skp`, depois
`.../cliente/novo` com o redirect_uri real) — evita `client_secret` em texto
puro no controle de versão. Preferir essa via se possível; a migration SQL
acima fica como registro/documentação alternativa.

## 2. Backend .NET (`eSKQaWeb.Api`) — escopo de arquivos a alterar

Fora deste repositório, no projeto local (`C:\Sistema\skpQa\api`). Segue a
estrutura modular já existente (`Modules/Auth/`) — nenhum módulo novo,
tudo entra dentro de `Auth` porque é autenticação, só que por uma segunda
via. Nenhum pacote NuGet novo deve ser necessário: `Microsoft.IdentityModel.Tokens`
e `System.IdentityModel.Tokens.Jwt` já estão referenciados (é o que sustenta
o `AddJwtBearer` existente em `AddJwtAuth`) e cobrem validação manual de
JWT por JWKS também.

### 2.1 `Modules/Auth/AuthEndpoints.cs` — editar

Adicionar rota nova no grupo existente, ao lado de `/login`:
```csharp
group.MapPost("/sso/callback", SsoCallback).AllowAnonymous();
```
Novo handler `SsoCallback`, no mesmo estilo do `Login` existente (mesmo
`switch` de erro → status HTTP, mesmo formato `{ error, code }`):
```csharp
static async Task<IResult> SsoCallback(SsoCallbackRequest req, AuthService svc, CancellationToken ct)
{
    var result = await svc.LoginViaSsoAsync(req, ct);
    if (result.IsSuccess)
        return Results.Ok(result.Value);

    return result.Error switch
    {
        AuthService.ErrUserNotProvisioned => Results.Json(
            new { error = "Usuário não cadastrado no SKP. Contate o administrador.", code = AuthService.ErrUserNotProvisioned },
            statusCode: StatusCodes.Status403Forbidden),
        AuthService.ErrNoQualityProfile => Results.Json(
            new { error = "Usuário sem perfil de qualidade.", code = AuthService.ErrNoQualityProfile },
            statusCode: StatusCodes.Status403Forbidden),
        AuthService.ErrSsoNoPortalAccess => Results.Json(
            new { error = "Usuário sem acesso ao SKP no portal.", code = AuthService.ErrSsoNoPortalAccess },
            statusCode: StatusCodes.Status403Forbidden),
        _ => Results.Json(
            new { error = "Não foi possível concluir o login via portal.", code = result.Error },
            statusCode: StatusCodes.Status401Unauthorized)
    };
}
```
`AddAuthModule` (mesmo arquivo) ganha os registros de DI novos (ver 2.4/2.5
abaixo): `services.AddHttpClient<PortalSsoClient>();` e
`services.AddSingleton<SupabaseJwtValidator>();`.

### 2.2 Contrato HTTP — editar o arquivo de records (`AuthContracts.cs` ou
equivalente, onde já estão `LoginRequest`/`LoginResponse`/`AuthUserDto`)

```csharp
/// <summary>Corpo do POST /api/auth/sso/callback: o code recebido do portal.</summary>
public sealed record SsoCallbackRequest(string Code);
```
Nenhuma mudança em `LoginResponse`/`AuthUserDto` — o callback SSO devolve
exatamente o mesmo shape do login local, propositalmente (é o que permite
zero mudança no frontend além da nova rota `/callback`).

### 2.3 `Modules/Auth/AuthService.cs` — editar

Novos códigos de erro (mesmo padrão `const string Err... = "..."` de
`ErrInvalidCredentials`/`ErrNoQualityProfile`):
```csharp
public const string ErrUserNotProvisioned = "user_not_provisioned";
public const string ErrSsoNoPortalAccess  = "sso_no_portal_access";
public const string ErrSsoInvalidGrant    = "sso_invalid_grant";
public const string ErrSsoExpired         = "sso_expired";
public const string ErrSsoAlreadyUsed     = "sso_already_used";
public const string ErrSsoInvalidClient   = "sso_invalid_client";
public const string ErrSsoNetworkError    = "sso_network_error";
public const string ErrSsoInvalidToken    = "sso_invalid_token";
```
Novo método (paralelo ao `LoginAsync` existente, reaproveitando
`JwtTokenFactory` e o repositório):
```csharp
public async Task<Result<LoginResponse>> LoginViaSsoAsync(SsoCallbackRequest req, CancellationToken ct)
{
    var exchange = await _portalClient.ExchangeCodeAsync(req.Code, ct);
    if (!exchange.IsSuccess)
        return Result<LoginResponse>.Fail(MapPortalError(exchange.Error)); // invalid_grant/expired/already_used/invalid_client/network_error → ErrSso*

    var claims = _jwtValidator.Validate(exchange.Value.AccessToken); // lança/retorna falha em assinatura inválida → ErrSsoInvalidToken
    if (claims is null)
        return Result<LoginResponse>.Fail(ErrSsoInvalidToken);

    var papeisSkp = claims.AcessosSkp; // claims["app_metadata"]["acessos"]["skp"], lista de códigos
    if (papeisSkp.Count == 0)
        return Result<LoginResponse>.Fail(ErrSsoNoPortalAccess);

    var userRow = await _repository.FindByEmailAsync(claims.Email, ct); // novo método, ver 2.4
    if (userRow is null)
        return Result<LoginResponse>.Fail(ErrUserNotProvisioned);

    // dali pra frente, idêntico ao fim do LoginAsync local: monta AuthUserDto
    // a partir de userRow (Usuario.Id/Nome/PerfilDescricao LOCAIS, não os do portal),
    // emite token via _jwtTokenFactory, devolve LoginResponse.
    return Result<LoginResponse>.Ok(BuildLoginResponse(userRow));
}
```
Extrair `BuildLoginResponse(SkpUserRow)` do `LoginAsync` atual, se ainda não
for uma função separada — evita duplicar a lógica de "linha do banco vira
`LoginResponse`" entre os dois fluxos.

### 2.4 `Modules/Auth/AuthRepository.cs` — editar

Novo método ao lado do que já busca por login/senha, mesma query base
(JOIN `dbo.Usuario`/`dbo.Perfil`), filtrando por e-mail em vez de
login+senha:
```csharp
public async Task<SkpUserRow?> FindByEmailAsync(string email, CancellationToken ct)
{
    const string sql = @"
        select u.Id, u.Nome, p.Descricao as PerfilDescricao
        from dbo.Usuario u
        join dbo.Perfil p on p.Id = u.PerfilId
        where u.Email = @Email"; // confirmar nome real da coluna de e-mail em dbo.Usuario
    using var conn = _connectionFactory.CreateConnection();
    return await conn.QuerySingleOrDefaultAsync<SkpUserRow>(sql, new { Email = email });
}
```
**Ponto a confirmar no projeto real**: qual é o nome exato da coluna de
e-mail em `dbo.Usuario` (pode não se chamar `Email` — checar o schema/o
`LoginAsync` atual, que hoje busca por login, não por e-mail. Se
`dbo.Usuario` não tiver e-mail cadastrado hoje, isso é um bloqueio a
resolver antes do resto — sem e-mail confiável, não dá pra casar identidade
do portal com o usuário local).

### 2.5 Novo: `Modules/Auth/PortalSsoClient.cs`

Cliente HTTP dedicado, injetado via `AddHttpClient<PortalSsoClient>()`
(reaproveita `IHttpClientFactory`, já é o padrão idiomático em minimal APIs
.NET pra chamadas HTTP de saída):
```csharp
public sealed class PortalSsoClient(HttpClient http, IOptions<PortalSsoOptions> options)
{
    public async Task<Result<PortalTokenResponse>> ExchangeCodeAsync(string code, CancellationToken ct)
    {
        var resp = await http.PostAsJsonAsync(options.Value.PortalTokenUrl,
            new { code, client_secret = options.Value.SkpClientSecret }, ct);

        if (resp.IsSuccessStatusCode)
            return Result<PortalTokenResponse>.Ok(await resp.Content.ReadFromJsonAsync<PortalTokenResponse>(ct));

        var body = await resp.Content.ReadFromJsonAsync<PortalErrorResponse>(ct);
        return Result<PortalTokenResponse>.Fail(body?.Error ?? "network_error");
    }
}

public sealed record PortalTokenResponse(string AccessToken, string? RefreshToken);
public sealed record PortalErrorResponse(string Error);
```
Contrato idêntico ao `POST /token` do portal (`portal/app/routers/oauth.py`
— sem headers especiais, JSON puro, resposta `{access_token, refresh_token}`
ou `{error}`).

### 2.6 Novo: `Modules/Auth/SupabaseJwtValidator.cs`

Validação manual e independente do JWT do Supabase — **não reaproveitar**
o esquema `AddJwtBearer` já configurado em `AddJwtAuth` (esse valida o
token que a própria SKP emite; emissor e chave são outros). Usa as mesmas
libs já referenciadas pelo projeto:
```csharp
public sealed class SupabaseJwtValidator(IOptions<PortalSsoOptions> options, HttpClient http)
{
    public async Task<SupabaseClaims?> ValidateAsync(string token, CancellationToken ct)
    {
        var jwks = await FetchJwksAsync(ct); // GET options.Value.SupabaseJwksUrl, cachear com expiração curta
        var handler = new JwtSecurityTokenHandler();
        var parameters = new TokenValidationParameters
        {
            ValidateIssuer = false,
            ValidateAudience = true,
            ValidAudience = "authenticated",
            ValidAlgorithms = [SecurityAlgorithms.EcdsaSha256], // ES256
            IssuerSigningKeys = jwks.Keys,
        };
        try
        {
            var principal = handler.ValidateToken(token, parameters, out _);
            return SupabaseClaims.FromPrincipal(principal); // extrai email, sub, app_metadata.acessos.skp
        }
        catch (SecurityTokenException)
        {
            return null;
        }
    }
}
```
`SupabaseClaims.AcessosSkp` faz o parse de `app_metadata.acessos.skp` (a
claim é um objeto JSON aninhado, não uma claim plana — precisa desserializar
o claim `app_metadata` como JSON e navegar até `acessos.skp`, não dá pra
ler direto via `principal.FindFirst`).

### 2.7 `Program.cs` — editar

- `builder.Services.Configure<PortalSsoOptions>(builder.Configuration.GetSection("PortalSso"));`
- Nenhuma mudança em `AddJwtAuth`/`UseAuthentication`/`UseAuthorization` —
  o endpoint SSO é `AllowAnonymous()` e faz sua própria validação manual.

### 2.8 `appsettings.json` (e `appsettings.Development.json`) — editar

Nova seção:
```json
"PortalSso": {
  "PortalTokenUrl": "http://portal.lab.internal/token",
  "SkpClientSecret": "<client_secret cadastrado em app_clients para 'skp'>",
  "SupabaseJwksUrl": "http://supabase.lab.internal/auth/v1/.well-known/jwks.json"
}
```
Em produção, `SkpClientSecret` deve vir de variável de ambiente/secret
store, não commitado — mesma ressalva que o README raiz já faz sobre
`client_secret` em texto puro (seção 8.5).

### 2.9 CORS

Como front e API agora ficam atrás do mesmo hostname público via Caddy
(`skp.ind.lab.internal`, roteado por path), esse endpoint não depende de
CORS liberado — mas não é preciso remover a config existente.

## 3. Frontend (Vite) — fora deste repositório, no projeto local

- `VITE_API_BASE_URL` deve ficar **vazio** (não `/api` — o próprio código em
  `apiUrl(path)` já concatena `/api` na frente; setar `/api` duplicaria o
  prefixo). Rebuild (`npm run build`) e redeploy do `dist` em
  `C:\Sistema\skpQa\www` depois da mudança no `.env`.
- Nova rota client-side `/callback` (roteador do SPA): lê `?code=` da URL,
  chama `http.post('/auth/sso/callback', { code })` (usa o `http` client já
  existente em `qualidade`-equivalente, ver arquivo colado pelo usuário),
  guarda o `token`/`user` retornado do mesmo jeito que o fluxo de
  `/auth/login` já guarda (mesmo `devAuth`), e redireciona pra tela inicial
  autenticada.
- Tratar erro (SSO callback falhou, usuário sem acesso, code inválido/expirado)
  mostrando mensagem — não precisa ser página dedicada, pode reaproveitar o
  tratamento de erro de login existente.

## Verificação de ponta a ponta

1. Aplicar o bloco final do Caddyfile na VM (seção "Infra" acima) e
   confirmar `http://skp.ind.lab.internal` responde (frontend) e
   `http://skp.ind.lab.internal/api/...` chega na API (sem 502).
2. Rodar a migration/cadastro admin do app `skp` no portal, garantir que o
   usuário de teste tem papel em `acessos["skp"]` no JWT (mesma validação já
   feita pra `qualidade` no README seção 7.6) e que existe um usuário
   correspondente em `dbo.Usuario` com o mesmo e-mail.
3. Fluxo manual: portal → clicar no tile da SKP → `GET /authorize` → redirect
   pro `/callback` da SKP com `code` → troca no `/api/auth/sso/callback` →
   sessão criada → tela inicial da SKP autenticada.
4. Confirmar que login local (`/api/auth/login`, usuário/senha) continua
   funcionando sem nenhuma alteração de comportamento — prova de que a
   integração foi puramente aditiva.
5. Testar o caso de e-mail do portal sem usuário correspondente local —
   deve negar com mensagem clara, não crashar nem criar usuário.
