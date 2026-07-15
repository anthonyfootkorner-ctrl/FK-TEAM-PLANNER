-- ============================================================
--  STOCKFLOW.AI — Mesure d'impact (ventes + euros sur les transferts)
--  A coller dans Supabase > SQL Editor, puis "Run".
--
--  Ajoute une colonne `impact` (jsonb) sur les runs. Elle est remplie a la
--  generation SUIVANTE : on y stocke, pour le run precedent, les ventes
--  realisees sur les references transferees (articles, CA, marge) au global
--  et par magasin.
-- ============================================================

alter table public.stockflow_runs
  add column if not exists impact jsonb;
