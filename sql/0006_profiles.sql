-- public.profiles: extensao 1:1 de auth.users para dados de perfil que nao
-- pertencem ao GoTrue (hoje so o nome de exibicao).
--
-- auth.users continua estritamente somente-leitura do lado do app (ver
-- db_admin.py, secao "Usuarios") - esta tabela NUNCA e escrita diretamente
-- pelo backend. Ela e mantida em sincronia por um trigger que so LE
-- auth.users (via NEW, dentro do proprio evento de insert/update) e
-- ESCREVE em public.profiles - o padrao de trigger explicitamente permitido
-- pela politica de acesso a auth.users. Toda escrita em auth.users continua
-- indo exclusivamente pela Admin API (app/supabase_admin_client.py):
-- ao criar um usuario, o admin passa `user_metadata={"nome": ...}`, o GoTrue
-- grava isso em auth.users.raw_user_meta_data (e automaticamente expoe como
-- claim `user_metadata.nome` no JWT), e o trigger abaixo espelha esse valor
-- para public.profiles.nome sempre que raw_user_meta_data mudar.

create table if not exists public.profiles (
  id            uuid primary key references auth.users(id) on delete cascade,
  nome          text,
  criado_em     timestamptz not null default now(),
  atualizado_em timestamptz not null default now()
);

alter table public.profiles enable row level security;

drop policy if exists "usuario le o proprio profile" on public.profiles;
create policy "usuario le o proprio profile" on public.profiles
  for select to authenticated
  using ( (select auth.uid()) = id );

-- Sem policy de insert/update/delete: profiles so e escrita pelo trigger
-- abaixo (security definer) ou pela conexao asyncpg privilegiada do portal -
-- nunca pelo usuario final via RLS.

create or replace function public.sync_profile_from_auth_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.profiles (id, nome, atualizado_em)
  values (new.id, new.raw_user_meta_data ->> 'nome', now())
  on conflict (id) do update
    set nome = excluded.nome,
        atualizado_em = now();
  return new;
end;
$$;

drop trigger if exists on_auth_user_created_or_updated on auth.users;
create trigger on_auth_user_created_or_updated
  after insert or update of raw_user_meta_data on auth.users
  for each row execute function public.sync_profile_from_auth_user();

-- Backfill: usuarios criados antes desta migration nao disparam o trigger
-- retroativamente. Le auth.users (select, permitido) e escreve em
-- public.profiles (nome fica null se raw_user_meta_data nunca teve 'nome').
insert into public.profiles (id, nome)
select id, raw_user_meta_data ->> 'nome'
from auth.users
on conflict (id) do nothing;
