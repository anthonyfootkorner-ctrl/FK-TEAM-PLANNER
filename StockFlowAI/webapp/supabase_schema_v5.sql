-- ============================================================
--  STOCKFLOW.AI — Validation d'expedition par les magasins
--  A coller dans Supabase > SQL Editor, puis "Run".
--
--  Quand un magasin a coche "prepare" toutes les lignes d'une
--  expedition (vers une destination), il VALIDE l'expedition.
--  Une ligne = un couple (run, expediteur, destinataire).
-- ============================================================

create table if not exists public.stockflow_shipments (
  run_id       uuid references public.stockflow_runs(id) on delete cascade,
  expediteur   text not null,
  destinataire text not null,
  statut       text not null default 'validee',
  validated_by uuid references auth.users(id),
  validated_at timestamptz default now(),
  primary key (run_id, expediteur, destinataire)
);

alter table public.stockflow_shipments enable row level security;

-- lecture : tout utilisateur connecte (equipe interne)
drop policy if exists sf_ship_read on public.stockflow_shipments;
create policy sf_ship_read on public.stockflow_shipments
  for select to authenticated using (true);

-- creation / mise a jour / suppression : utilisateur connecte
drop policy if exists sf_ship_insert on public.stockflow_shipments;
create policy sf_ship_insert on public.stockflow_shipments
  for insert to authenticated with check (true);

drop policy if exists sf_ship_update on public.stockflow_shipments;
create policy sf_ship_update on public.stockflow_shipments
  for update to authenticated using (true) with check (true);

drop policy if exists sf_ship_delete on public.stockflow_shipments;
create policy sf_ship_delete on public.stockflow_shipments
  for delete to authenticated using (true);
