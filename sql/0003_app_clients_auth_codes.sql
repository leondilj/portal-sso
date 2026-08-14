-- README.md secao 8.1: tabelas de suporte ao mini authorization code flow
-- do portal (app_clients cadastra cada aplicacao cliente + seu secret e
-- redirect_uris; auth_codes guarda os codes de uso unico emitidos pelo
-- GET /authorize e consumidos pelo POST /token).
--
-- Sem policies de RLS: so o backend do portal acessa essas tabelas, via uma
-- conexao Postgres privilegiada (asyncpg), nunca via PostgREST/RLS.

create table if not exists public.app_clients (
  aplicacao_id  text primary key references public.aplicacoes(id) on delete cascade,
  client_secret text not null,
  redirect_uris text[] not null
);

create table if not exists public.auth_codes (
  code          text primary key,
  user_id       uuid not null references auth.users(id) on delete cascade,
  aplicacao_id  text not null references public.aplicacoes(id) on delete cascade,
  redirect_uri  text not null,
  access_token  text not null,
  refresh_token text,
  expira_em     timestamptz not null,
  usado_em      timestamptz
);

create index if not exists idx_auth_codes_expira_em on public.auth_codes(expira_em);

alter table public.app_clients enable row level security;
alter table public.auth_codes  enable row level security;
