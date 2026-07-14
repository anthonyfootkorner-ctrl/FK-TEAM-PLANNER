-- ============================================================
--  STOCKFLOW.AI — Vue magasin (role terrain)
--  A coller dans Supabase > SQL Editor, puis "Run".
--  Cree :
--    1) stockflow_user_stores      : quel compte voit quel magasin
--    2) stockflow_urgent_requests  : demandes urgentes magasin -> admin
-- ============================================================

-- 1) Mapping compte -> magasin -------------------------------
-- Un compte present ici est un compte MAGASIN (il ne voit que son magasin).
-- Un compte absent d'ici est traite comme ADMIN (vue complete).
create table if not exists public.stockflow_user_stores (
  user_id    uuid primary key references auth.users(id) on delete cascade,
  magasin    text not null,
  created_at timestamptz default now()
);

alter table public.stockflow_user_stores enable row level security;

-- chaque utilisateur peut lire SA propre affectation (pour savoir son magasin)
drop policy if exists us_read_own on public.stockflow_user_stores;
create policy us_read_own on public.stockflow_user_stores
  for select to authenticated using (auth.uid() = user_id);
-- (l'admin cree/modifie les affectations via ce SQL Editor, cf. plus bas)


-- 2) Demandes urgentes ---------------------------------------
create table if not exists public.stockflow_urgent_requests (
  id         uuid primary key default gen_random_uuid(),
  magasin    text not null,
  reference  text not null,
  taille     text,
  quantite   int  default 1,
  motif      text,
  statut     text not null default 'en_attente',   -- en_attente | validee | refusee
  created_by uuid references auth.users(id),
  created_at timestamptz default now(),
  decided_by uuid references auth.users(id),
  decided_at timestamptz
);

alter table public.stockflow_urgent_requests enable row level security;

-- lecture : tout utilisateur connecte (equipe interne)
drop policy if exists ur_read on public.stockflow_urgent_requests;
create policy ur_read on public.stockflow_urgent_requests
  for select to authenticated using (true);

-- creation : un utilisateur connecte, en son nom
drop policy if exists ur_insert on public.stockflow_urgent_requests;
create policy ur_insert on public.stockflow_urgent_requests
  for insert to authenticated with check (auth.uid() = created_by);

-- decision (valider / refuser) : un utilisateur connecte (admin)
drop policy if exists ur_update on public.stockflow_urgent_requests;
create policy ur_update on public.stockflow_urgent_requests
  for update to authenticated using (true) with check (true);


-- ============================================================
--  AFFECTER UN MAGASIN A UN COMPTE
--  1. Cree d'abord l'utilisateur dans : Authentication > Users > Add user
--     (ex. toulouse@fk.local + un mot de passe).
--  2. Recupere son UUID (colonne "User UID" dans la liste).
--  3. Lance l'insert ci-dessous (decommente et remplace) :
--
--  insert into public.stockflow_user_stores (user_id, magasin)
--  values ('00000000-0000-0000-0000-000000000000', 'TOULOUSE')
--  on conflict (user_id) do update set magasin = excluded.magasin;
--
--  Les noms de magasin doivent correspondre EXACTEMENT a ceux des
--  transferts (ex. TOULOUSE, LYON, ANNEMASSE, FKLILLE2...).
-- ============================================================
