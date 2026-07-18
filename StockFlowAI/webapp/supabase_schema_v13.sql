-- ============================================================
--  STOCKFLOW.AI — Désignation produit sur les transferts
--  A coller dans Supabase > SQL Editor, puis "Run".
--
--  Libellé produit (si l'export le fournit) porté sur chaque transfert,
--  pour l'afficher dans les bons de préparation magasin (marque +
--  désignation) et regrouper par marque.
-- ============================================================

alter table public.stockflow_transfers
  add column if not exists designation text;
