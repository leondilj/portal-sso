-- Registra o proprio portal como uma "aplicacao" no modelo ja existente,
-- para que a area administrativa (/admin) seja protegida pelo MESMO
-- mecanismo de papel-por-aplicacao usado por qualidade/vendas/pcp - sem
-- sistema de permissao paralelo. Zero mudanca no hook (0002): ele ja
-- agrega usuario_papeis/papeis/aplicacoes para QUALQUER linha, incluindo
-- esta.
--
-- 'portal' fica ativo=true (o hook em 0002 exige `a.ativo` pra agregar o
-- papel no JWT - se ficasse inativo, ninguem NUNCA teria acessos.portal
-- populado e require_admin ficaria permanentemente impossivel de
-- satisfazer). Isso e seguro porque app/db.py's fetch_apps_for_acessos
-- agora faz inner join com app_clients - so vira tile clicavel quem esta
-- de fato configurado como cliente OAuth, e 'portal' NUNCA tera uma linha
-- em app_clients (nao e um app cliente redirecionado via /authorize, e o
-- proprio portal). Sem esse join no codigo, esta migration deixaria
-- qualquer admin logado com uma tile "Portal SSO" que daria 502 ao
-- clicar - confirme que o fix de fetch_apps_for_acessos ja esta deployado
-- antes de aplicar esta migration.
--
-- BOOTSTRAP MANUAL (rode uma vez, fora deste arquivo, contra o Postgres do
-- lab, DEPOIS de aplicar esta migration): nao existe nenhum admin ainda
-- para conceder o primeiro papel pela UI (problema do ovo e da galinha).
--
--   insert into public.usuario_papeis (user_id, papel_id)
--   select u.id, p.id
--   from auth.users u, public.papeis p
--   where u.email = 'SEU_EMAIL_AQUI'
--     and p.aplicacao_id = 'portal' and p.codigo = 'admin'
--   on conflict (user_id, papel_id) do nothing;
--
-- Esse usuario precisa dar logout/login (ou esperar o token expirar e
-- renovar) depois disso para o JWT carregar app_metadata.acessos.portal -
-- mesma propagacao ja documentada para qualquer concessao de papel. Todo
-- admin seguinte pode ser promovido direto pela UI em /admin/usuarios.

insert into public.aplicacoes (id, nome, descricao, url, icone, ativo, ordem)
values ('portal', 'Portal SSO', 'Area administrativa do proprio portal', '/', null, true, 0)
on conflict (id) do nothing;

insert into public.papeis (aplicacao_id, codigo, nome, descricao)
values ('portal', 'admin', 'Administrador',
        'Acesso a area de gestao do portal (sistemas, perfis e usuarios)')
on conflict (aplicacao_id, codigo) do nothing;
