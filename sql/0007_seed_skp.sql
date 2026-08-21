-- Registro da primeira aplicacao cliente real conectada ao portal: SKP
-- (eSKQaWeb, sistema de qualidade da Kover), rodando em IIS numa maquina
-- Windows na rede do lab (skp.ind.lab.internal, roteada via Caddy).
--
-- client_secret abaixo e um PLACEHOLDER — trocar antes de aplicar, ou
-- preferir cadastrar via area /admin do portal (POST /admin/sistemas/novo
-- + .../cliente/novo), que gera o secret automaticamente e evita texto
-- puro no controle de versao. Este arquivo fica como registro/alternativa
-- documentada, seguindo o padrao de sql/0004_seed_dev_data.sql.
--
-- Decisao de integracao (ver plano da sessao): o portal decide identidade
-- e acesso (quem entra), mas o papel local do usuario no SKP continua
-- vindo de dbo.Usuario/dbo.Perfil — os papeis abaixo espelham o vocabulario
-- ja existente no SKP (database/manual/010_quality_roles.sql) por
-- consistencia, mesmo que ainda nao decidam nada sozinhos no fluxo atual.

insert into public.aplicacoes (id, nome, descricao, url, ordem) values
  ('skp', 'SKP - Qualidade', 'Sistema Kover de Qualidade', 'http://skp.ind.lab.internal', 4)
on conflict (id) do nothing;

insert into public.papeis (aplicacao_id, codigo, nome) values
  ('skp', 'qualidade',   'Qualidade'),
  ('skp', 'supervisor',  'Supervisor Qualidade'),
  ('skp', 'faturamento', 'Faturamento')
on conflict (aplicacao_id, codigo) do nothing;

insert into public.app_clients (aplicacao_id, client_secret, redirect_uris) values
  ('skp', 'segredo-skp-trocar', array['http://skp.ind.lab.internal/callback'])
on conflict (aplicacao_id) do nothing;
