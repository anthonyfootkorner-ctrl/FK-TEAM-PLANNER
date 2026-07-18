-- ============================================================
--  STOCKFLOW.AI — Valorisation cumulative des réassorts
--  A coller dans Supabase > SQL Editor, puis "Run".
--
--  Mesure, semaine après semaine, l'argent généré par les pièces
--  déplacées — SÉPARÉMENT :
--   * type 'central'    : réassort CENTRAL -> magasin ;
--   * type 'interstore' : transfert magasin -> magasin.
--
--  Chaque ligne = une « cohorte » (run source × type × expéditeur ×
--  destinataire × référence). On accumule les ventes réalisées à
--  destination sur la référence, PLAFONNÉES au nb de pièces envoyées
--  (on ne crédite jamais plus que ce qu'on a bougé), à partir de la
--  date du réassort, sans limite de temps. `last_date` évite le
--  double comptage entre deux fichiers de ventes qui se recouvrent.
--
--  Crédit expéditeur : pour l'inter-magasins, la valeur est portée par
--  l'expéditeur (« l'argent que MES envois ont rapporté ailleurs ») ET
--  visible par destinataire.
-- ============================================================

create table if not exists public.stockflow_valorisation (
  id            bigint generated always as identity primary key,
  source_run_id uuid references public.stockflow_runs(id) on delete cascade,
  type          text not null check (type in ('central','interstore')),
  expediteur    text not null,           -- 'CENTRAL' pour le réassort central
  destinataire  text not null,
  reference     text not null,
  sent_qty      integer not null default 0,
  run_date      date,                    -- début d'attribution (date du réassort)
  cumul_units   integer not null default 0,
  cumul_ca      numeric not null default 0,
  cumul_marge   numeric not null default 0,
  last_date     date,                    -- dernière date de vente déjà comptée
  closed        boolean not null default false,  -- plafond atteint
  updated_at    timestamptz default now(),
  unique (source_run_id, type, expediteur, destinataire, reference)
);

create index if not exists sf_valo_dest on public.stockflow_valorisation(destinataire);
create index if not exists sf_valo_exp  on public.stockflow_valorisation(expediteur);
create index if not exists sf_valo_type on public.stockflow_valorisation(type);
create index if not exists sf_valo_open on public.stockflow_valorisation(closed);

alter table public.stockflow_valorisation enable row level security;

-- lecture : tout utilisateur connecté (filtrage par magasin côté interface).
-- écriture : service_role (moteur), exempté de RLS.
drop policy if exists sf_valo_read on public.stockflow_valorisation;
create policy sf_valo_read on public.stockflow_valorisation
  for select to authenticated using (true);
