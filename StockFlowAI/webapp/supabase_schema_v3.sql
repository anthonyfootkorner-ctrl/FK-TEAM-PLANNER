-- ============================================================
--  STOCKFLOW.AI — Autoriser PLUSIEURS magasins par compte
--  A coller dans Supabase > SQL Editor, puis "Run".
--  (a lancer APRES supabase_schema_v2.sql)
-- ============================================================

-- Cas 1 : la table existe deja (creee par schema_v2) avec 1 magasin/compte.
--         On remplace la cle (user_id) par une cle composite (user_id, magasin)
--         pour autoriser plusieurs lignes par utilisateur.
alter table public.stockflow_user_stores
  drop constraint if exists stockflow_user_stores_pkey;

alter table public.stockflow_user_stores
  add primary key (user_id, magasin);

-- Cas 2 : la table n'existe pas encore -> version deja multi-magasins.
create table if not exists public.stockflow_user_stores (
  user_id    uuid references auth.users(id) on delete cascade,
  magasin    text not null,
  created_at timestamptz default now(),
  primary key (user_id, magasin)
);
alter table public.stockflow_user_stores enable row level security;
drop policy if exists us_read_own on public.stockflow_user_stores;
create policy us_read_own on public.stockflow_user_stores
  for select to authenticated using (auth.uid() = user_id);


-- ============================================================
--  AFFECTER PLUSIEURS MAGASINS A UN COMPTE
--  (une ligne par magasin) :
--
--  insert into public.stockflow_user_stores (user_id, magasin) values
--    ('00000000-0000-0000-0000-000000000000', 'TOULOUSE'),
--    ('00000000-0000-0000-0000-000000000000', 'LYON'),
--    ('00000000-0000-0000-0000-000000000000', 'ANNEMASSE')
--  on conflict (user_id, magasin) do nothing;
--
--  -> Ce compte verra un selecteur pour basculer entre TOULOUSE / LYON /
--     ANNEMASSE. Un compte avec un seul magasin n'a pas de selecteur.
--
--  Retirer un magasin d'un compte :
--  delete from public.stockflow_user_stores
--   where user_id = '00000000-...' and magasin = 'LYON';
-- ============================================================
