-- README.md secao 7.3: Custom Access Token Hook.
-- Injeta em app_metadata.acessos um mapa {aplicacao_id: [codigo_do_papel, ...]}
-- com os papeis do usuario, para as aplicacoes clientes lerem direto do JWT.
--
-- ATENCAO (ordem de ativacao): so ative
--   GOTRUE_HOOK_CUSTOM_ACCESS_TOKEN_ENABLED=true
--   GOTRUE_HOOK_CUSTOM_ACCESS_TOKEN_URI=pg-functions://postgres/public/custom_access_token_hook
-- no .env do Supabase (e rode `sh run.sh recreate auth`) DEPOIS desta
-- migration ter sido aplicada. Se o GoTrue for configurado para chamar uma
-- funcao que ainda nao existe, todo login falha. Esse passo e feito na VM do
-- lab, fora deste repositorio.

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

-- Facil de esquecer e o sintoma e silencioso: sem essas tres policies o hook
-- roda sem erro e sempre devolve `acessos` vazio (supabase_auth_admin nao
-- consegue ler as tabelas por baixo do RLS sem elas).
drop policy if exists "auth admin le usuario_papeis" on public.usuario_papeis;
create policy "auth admin le usuario_papeis" on public.usuario_papeis
  as permissive for select to supabase_auth_admin using (true);

drop policy if exists "auth admin le papeis" on public.papeis;
create policy "auth admin le papeis" on public.papeis
  as permissive for select to supabase_auth_admin using (true);

drop policy if exists "auth admin le aplicacoes" on public.aplicacoes;
create policy "auth admin le aplicacoes" on public.aplicacoes
  as permissive for select to supabase_auth_admin using (true);
