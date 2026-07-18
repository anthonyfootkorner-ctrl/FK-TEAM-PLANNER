-- ============================================================
--  STOCKFLOW.AI — Classeur Excel des transferts inter-magasins
--  A coller dans Supabase > SQL Editor, puis "Run".
--
--  Chemin (dans le bucket Storage) du classeur Excel des transferts
--  inter-magasins (« intershop ») genere a chaque run : transferts,
--  synthese des flux, simulation avant/apres, cas non traites…
--  Il est aussi joint au meme e-mail que le reassort central.
-- ============================================================

alter table public.stockflow_runs
  add column if not exists transferts_excel text;
