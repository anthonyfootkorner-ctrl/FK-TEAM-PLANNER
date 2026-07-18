-- ============================================================
--  STOCKFLOW.AI — Total valorisé « depuis le début »
--  A coller dans Supabase > SQL Editor, puis "Run".
--
--  Accumulateur PERSISTANT (jamais purgé) : à chaque génération, on
--  y ajoute l'incrément valorisé de la semaine (par piste). Les
--  cohortes détaillées (stockflow_valorisation) sont purgées avec les
--  vieux runs, mais ce total, lui, reste — c'est le « depuis le début ».
-- ============================================================

create table if not exists public.stockflow_valo_total (
  type       text primary key check (type in ('central','interstore')),
  units      bigint  not null default 0,
  ca         numeric not null default 0,
  marge      numeric not null default 0,
  updated_at timestamptz default now()
);

-- lignes initiales (idempotent)
insert into public.stockflow_valo_total(type) values ('central'), ('interstore')
  on conflict (type) do nothing;

alter table public.stockflow_valo_total enable row level security;

drop policy if exists sf_valot_read on public.stockflow_valo_total;
create policy sf_valot_read on public.stockflow_valo_total
  for select to authenticated using (true);
