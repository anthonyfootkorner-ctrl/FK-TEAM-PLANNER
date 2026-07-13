-- ===========================================================================
-- STOCKFLOW.AI — schema Supabase (Postgres)
-- A executer dans : Supabase > SQL Editor. Idempotent (create if not exists).
-- Reutilise l'auth existante (auth.users) du projet FK Team Planner.
-- ===========================================================================

-- 1) Executions (une ligne par run du moteur) --------------------------------
create table if not exists public.stockflow_runs (
  id             uuid primary key default gen_random_uuid(),
  label          text,                    -- ex. "perimetre_14j"
  date_execution date,
  perimetre      text,                    -- ex. "24 boutiques actives"
  cible          int,                     -- couverture cible (jours)
  nb_transferts  int,
  kpis           jsonb,                   -- simulation avant/apres
  parametres     jsonb,                   -- parametres utilises
  created_at     timestamptz default now(),
  created_by     uuid references auth.users (id)
);

-- 2) Transferts recommandes --------------------------------------------------
create table if not exists public.stockflow_transfers (
  id              bigint generated always as identity primary key,
  run_id          uuid references public.stockflow_runs (id) on delete cascade,
  n               int,
  priorite        text,
  score           numeric,
  marque          text,
  expediteur      text,
  destinataire    text,
  reference       text,                   -- code-barre complet
  taille          text,
  quantite        numeric,
  cov_dest_avant  numeric,
  cov_dest_apres  numeric,
  grille_avant    text,
  grille_apres    text,
  dispo_finale    text,
  picking_prevu   numeric,
  motif           text
);
create index if not exists idx_sf_transfers_run   on public.stockflow_transfers (run_id);
create index if not exists idx_sf_transfers_dest  on public.stockflow_transfers (run_id, destinataire);
create index if not exists idx_sf_transfers_exp   on public.stockflow_transfers (run_id, expediteur);

-- 3) Revue (OK / NON) partagee entre utilisateurs ----------------------------
create table if not exists public.stockflow_reviews (
  id           bigint generated always as identity primary key,
  transfer_id  bigint references public.stockflow_transfers (id) on delete cascade,
  run_id       uuid   references public.stockflow_runs (id) on delete cascade,
  etat         text check (etat in ('ok','no')),
  commentaire  text,
  reviewer     uuid references auth.users (id) default auth.uid(),
  updated_at   timestamptz default now(),
  unique (transfer_id, reviewer)
);
create index if not exists idx_sf_reviews_run on public.stockflow_reviews (run_id);

-- ===========================================================================
-- Securite (RLS). Les runs/transferts sont pousses par le moteur avec la
-- cle service_role (qui contourne RLS). Les utilisateurs connectes peuvent
-- LIRE, et gerer LEURS PROPRES lignes de revue.
-- ===========================================================================
alter table public.stockflow_runs      enable row level security;
alter table public.stockflow_transfers enable row level security;
alter table public.stockflow_reviews   enable row level security;

-- Lecture pour tout utilisateur authentifie
drop policy if exists sf_runs_read on public.stockflow_runs;
create policy sf_runs_read on public.stockflow_runs
  for select to authenticated using (true);

drop policy if exists sf_transfers_read on public.stockflow_transfers;
create policy sf_transfers_read on public.stockflow_transfers
  for select to authenticated using (true);

drop policy if exists sf_reviews_read on public.stockflow_reviews;
create policy sf_reviews_read on public.stockflow_reviews
  for select to authenticated using (true);

-- Chaque utilisateur gere ses propres revues
drop policy if exists sf_reviews_insert on public.stockflow_reviews;
create policy sf_reviews_insert on public.stockflow_reviews
  for insert to authenticated with check (reviewer = auth.uid());

drop policy if exists sf_reviews_update on public.stockflow_reviews;
create policy sf_reviews_update on public.stockflow_reviews
  for update to authenticated using (reviewer = auth.uid()) with check (reviewer = auth.uid());

drop policy if exists sf_reviews_delete on public.stockflow_reviews;
create policy sf_reviews_delete on public.stockflow_reviews
  for delete to authenticated using (reviewer = auth.uid());

-- Vue pratique : transferts + agregat de revue (utile pour le frontend)
create or replace view public.stockflow_transfers_reviewed as
select t.*,
       r_self.etat        as mon_etat,
       r_self.commentaire as mon_commentaire,
       (select count(*) from public.stockflow_reviews r
         where r.transfer_id = t.id and r.etat = 'ok') as nb_ok,
       (select count(*) from public.stockflow_reviews r
         where r.transfer_id = t.id and r.etat = 'no') as nb_no
from public.stockflow_transfers t
left join public.stockflow_reviews r_self
  on r_self.transfer_id = t.id and r_self.reviewer = auth.uid();
