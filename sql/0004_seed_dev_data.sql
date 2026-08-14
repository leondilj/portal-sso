-- README.md secoes 7.4 e 8.1: dados de exemplo para desenvolvimento/lab.
--
-- NAO RODAR CONTRA UM AMBIENTE REAL/PRODUCAO: contem client_secret em texto
-- puro como placeholder ("segredo-*-trocar") e referencia um usuario de
-- teste (joao@lab.internal) que so existe se voce criou esse usuario no seu
-- Supabase local. O insert de usuario_papeis e um no-op seguro (via join)
-- se esse usuario nao existir.

insert into public.aplicacoes (id, nome, descricao, url, ordem) values
  ('qualidade', 'Qualidade', 'Controle de qualidade e laudos', 'http://qualidade.lab.internal', 1),
  ('vendas',    'Vendas',    'Pedidos e carteira de clientes', 'http://vendas.lab.internal',    2),
  ('pcp',       'PCP',       'Planejamento e controle',        'http://pcp.lab.internal',       3)
on conflict (id) do nothing;

insert into public.papeis (aplicacao_id, codigo, nome) values
  ('qualidade', 'gerente',  'Gerente'),
  ('qualidade', 'analista', 'Analista'),
  ('vendas',    'gerente',  'Gerente'),
  ('vendas',    'analista', 'Analista'),
  ('pcp',       'operador', 'Operador')
on conflict (aplicacao_id, codigo) do nothing;

insert into public.usuario_papeis (user_id, papel_id)
select u.id, p.id
from auth.users u, public.papeis p
where u.email = 'joao@lab.internal'
  and ( (p.aplicacao_id = 'qualidade' and p.codigo = 'gerente')
     or (p.aplicacao_id = 'vendas'    and p.codigo = 'analista') )
on conflict (user_id, papel_id) do nothing;

insert into public.app_clients (aplicacao_id, client_secret, redirect_uris) values
  ('qualidade', 'segredo-qualidade-trocar', array['http://qualidade.lab.internal/callback']),
  ('vendas',    'segredo-vendas-trocar',    array['http://vendas.lab.internal/callback'])
on conflict (aplicacao_id) do nothing;
