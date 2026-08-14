-- README.md secao 7.1 e 7.2: modelo de dados do portal SSO
-- (aplicacoes, papeis por aplicacao, papeis concedidos por usuario) + RLS.
--
-- Papel nao e atributo do usuario, e atributo da relacao usuario x aplicacao.

create table if not exists public.aplicacoes (
  id         text primary key,
  nome       text not null,
  descricao  text,
  url        text not null,
  icone      text,
  ativo      boolean not null default true,
  ordem      int not null default 0,
  criado_em  timestamptz not null default now()
);

create table if not exists public.papeis (
  id           uuid primary key default gen_random_uuid(),
  aplicacao_id text not null references public.aplicacoes(id) on delete cascade,
  codigo       text not null,
  nome         text not null,
  descricao    text,
  criado_em    timestamptz not null default now(),
  unique (aplicacao_id, codigo)
);

create table if not exists public.usuario_papeis (
  user_id       uuid not null references auth.users(id) on delete cascade,
  papel_id      uuid not null references public.papeis(id) on delete cascade,
  concedido_em  timestamptz not null default now(),
  concedido_por uuid references auth.users(id),
  primary key (user_id, papel_id)
);

create index if not exists idx_usuario_papeis_user on public.usuario_papeis(user_id);
create index if not exists idx_papeis_aplicacao on public.papeis(aplicacao_id);

alter table public.aplicacoes     enable row level security;
alter table public.papeis         enable row level security;
alter table public.usuario_papeis enable row level security;

drop policy if exists "ve proprios papeis" on public.usuario_papeis;
create policy "ve proprios papeis" on public.usuario_papeis
  for select to authenticated
  using ( (select auth.uid()) = user_id );

drop policy if exists "le aplicacoes" on public.aplicacoes;
create policy "le aplicacoes" on public.aplicacoes
  for select to authenticated using (true);

drop policy if exists "le papeis" on public.papeis;
create policy "le papeis" on public.papeis
  for select to authenticated using (true);

-- Sem policy de insert/update/delete: concessao de papeis so pelo backend
-- administrativo (Postgres com role privilegiada), que nao passa pelo RLS.
-- Nenhum usuario pode se auto-conceder acesso.
