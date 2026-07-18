-- ============================================================
--  STOCKFLOW.AI — Reassort central (CENTRAL -> boutiques)
--  A coller dans Supabase > SQL Editor, puis "Run".
--
--  Enchainement 'A + B' : le reassort central est calcule d'abord
--  (CENTRAL -> boutiques), sa sortie alimente le picking du moteur
--  inter-magasins. Cette table stocke la sortie A (propositions par
--  boutique) ; le fichier d'import Fastmag (sortie B) est depose dans
--  le Storage et reference par la colonne `fastmag_import` du run.
-- ============================================================

-- Sortie A : propositions de reassort central, une ligne par
-- (run, boutique, reference, taille).
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

-- lecture : tout utilisateur connecte (le filtrage par boutique se fait cote
-- interface, comme pour les transferts). Ecriture : service_role (moteur) —
-- exempte de RLS, aucune policy insert necessaire pour l'ecriture serveur.
drop policy if exists sf_reac_read on public.stockflow_reassort_central;
create policy sf_reac_read on public.stockflow_reassort_central
  for select to authenticated using (true);

-- Sortie B : chemin du fichier d'import Fastmag (dans le bucket Storage).
alter table public.stockflow_runs
  add column if not exists fastmag_import text;
