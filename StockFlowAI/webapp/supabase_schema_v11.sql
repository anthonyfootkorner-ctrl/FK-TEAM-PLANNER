-- ============================================================
--  STOCKFLOW.AI — Classeur Excel du réassort central
--  A coller dans Supabase > SQL Editor, puis "Run".
--
--  Chemin (dans le bucket Storage) du classeur Excel récap généré à
--  chaque réassort central (Synthèse, Tous transferts, une feuille par
--  magasin, alertes…), comme l'outil historique. Il est aussi joint à
--  l'e-mail récap envoyé à la génération.
-- ============================================================

alter table public.stockflow_runs
  add column if not exists reassort_excel text;
