-- ============================================================================
--  STOCKFLOW.AI — SCRIPT SQL COMPLET (v6 -> v13)
--  A coller dans Supabase > SQL Editor, puis « Run ».
--
--  100 % idempotent : « if not exists » / « on conflict do nothing » partout.
--  Tu peux le relancer autant de fois que tu veux, il ne casse rien et
--  n'efface aucune donnee. Il rattrape tout ce qui manque d'un coup.
--
--  (La fonction « references a exclure des reassorts » n'ajoute AUCUNE table :
--   elle passe par le fichier charge a la generation, rien a faire ici.)
-- ============================================================================


-- ── v6 · Mesure d'impact (ventes + euros sur les references transferees) ────
alter table public.stockflow_runs
  add column if not exists impact jsonb;


-- ── v7 · Reassort central (CENTRAL -> boutiques) + import Fastmag ───────────
create table if not exists public.stockflow_reassort_central (
  id            bigint generated always as identity primary key,
  run_id        uuid references public.stockflow_runs(id) on delete cascade,
  boutique      text not null,
  reference     text not null,
  taille        text not null,
  marque        text,
  qte           integer not null default 0,
  priorite      text,
  commentaire   text,
  couverture_j  numeric,
  besoin        integer,
  stock         integer,
  tailles_apres text
);
create index if not exists sf_reac_run  on public.stockflow_reassort_central(run_id);
create index if not exists sf_reac_bout on public.stockflow_reassort_central(run_id, boutique);
alter table public.stockflow_reassort_central enable row level security;
drop policy if exists sf_reac_read on public.stockflow_reassort_central;
create policy sf_reac_read on public.stockflow_reassort_central
  for select to authenticated using (true);

alter table public.stockflow_runs
  add column if not exists fastmag_import text;


-- ── v8 · Donneurs (proposition de depannage sur demande urgente) ────────────
create table if not exists public.stockflow_donors (
  id           bigint generated always as identity primary key,
  run_id       uuid references public.stockflow_runs(id) on delete cascade,
  magasin      text not null,
  reference    text not null,
  taille       text not null,
  qte_don      integer not null default 0,
  couverture_j numeric,
  ventes_jour  numeric,
  motif        text
);
create index if not exists sf_don_run on public.stockflow_donors(run_id);
create index if not exists sf_don_ref on public.stockflow_donors(reference, taille);
alter table public.stockflow_donors enable row level security;
drop policy if exists sf_don_read on public.stockflow_donors;
create policy sf_don_read on public.stockflow_donors
  for select to authenticated using (true);


-- ── v9 · Valorisation cumulative des reassorts (central / inter-magasins) ───
create table if not exists public.stockflow_valorisation (
  id            bigint generated always as identity primary key,
  source_run_id uuid references public.stockflow_runs(id) on delete cascade,
  type          text not null check (type in ('central','interstore')),
  expediteur    text not null,           -- 'CENTRAL' pour le reassort central
  destinataire  text not null,
  reference     text not null,
  sent_qty      integer not null default 0,
  run_date      date,                    -- debut d'attribution (date du reassort)
  cumul_units   integer not null default 0,
  cumul_ca      numeric not null default 0,
  cumul_marge   numeric not null default 0,
  last_date     date,                    -- derniere date de vente deja comptee
  closed        boolean not null default false,
  updated_at    timestamptz default now(),
  unique (source_run_id, type, expediteur, destinataire, reference)
);
create index if not exists sf_valo_dest on public.stockflow_valorisation(destinataire);
create index if not exists sf_valo_exp  on public.stockflow_valorisation(expediteur);
create index if not exists sf_valo_type on public.stockflow_valorisation(type);
create index if not exists sf_valo_open on public.stockflow_valorisation(closed);
alter table public.stockflow_valorisation enable row level security;
drop policy if exists sf_valo_read on public.stockflow_valorisation;
create policy sf_valo_read on public.stockflow_valorisation
  for select to authenticated using (true);


-- ── v10 · Total valorise « depuis le debut » (persistant, jamais purge) ─────
create table if not exists public.stockflow_valo_total (
  type       text primary key check (type in ('central','interstore')),
  units      bigint  not null default 0,
  ca         numeric not null default 0,
  marge      numeric not null default 0,
  updated_at timestamptz default now()
);
insert into public.stockflow_valo_total(type) values ('central'), ('interstore')
  on conflict (type) do nothing;
alter table public.stockflow_valo_total enable row level security;
drop policy if exists sf_valot_read on public.stockflow_valo_total;
create policy sf_valot_read on public.stockflow_valo_total
  for select to authenticated using (true);


-- ── v11 · Classeur Excel du reassort central (chemin Storage) ───────────────
alter table public.stockflow_runs
  add column if not exists reassort_excel text;


-- ── v12 · Classeur Excel des transferts inter-magasins (chemin Storage) ─────
alter table public.stockflow_runs
  add column if not exists transferts_excel text;


-- ── v13 · Designation produit sur les transferts (bons de prepa) ────────────
alter table public.stockflow_transfers
  add column if not exists designation text;

-- ============================================================================
--  FIN. Si tout passe sans erreur rouge, la base est a jour.
-- ============================================================================
