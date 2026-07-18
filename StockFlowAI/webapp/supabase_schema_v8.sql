-- ============================================================
--  STOCKFLOW.AI — Donneurs (proposition de depannage sur demande urgente)
--  A coller dans Supabase > SQL Editor, puis "Run".
--
--  A chaque generation, le moteur pousse les DONNEURS (magasins en surplus
--  mobilisable) du run courant. Quand un magasin fait une demande urgente sur
--  une reference, l'admin voit quels magasins peuvent depanner (surplus + forte
--  couverture) sur cette reference. On ne conserve que la photo du run courant
--  (une demande urgente concerne le stock d'aujourd'hui).
-- ============================================================

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

-- lecture : tout utilisateur connecte (l'admin exploite la proposition). Ecriture :
-- service_role (moteur), exempte de RLS.
drop policy if exists sf_don_read on public.stockflow_donors;
create policy sf_don_read on public.stockflow_donors
  for select to authenticated using (true);
