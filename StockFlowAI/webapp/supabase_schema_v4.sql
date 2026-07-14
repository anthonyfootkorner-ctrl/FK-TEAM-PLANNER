-- ============================================================
--  STOCKFLOW.AI — Autoriser l'etat "difference" dans les revues
--  A coller dans Supabase > SQL Editor, puis "Run".
--
--  La table stockflow_reviews n'acceptait que etat in ('ok','no').
--  Les magasins signalent maintenant une DIFFERENCE en preparation
--  (etat='diff') -> on etend la contrainte. Sans ceci, le bouton
--  "⚠ Difference" echoue silencieusement (rien n'est enregistre).
-- ============================================================

alter table public.stockflow_reviews
  drop constraint if exists stockflow_reviews_etat_check;

alter table public.stockflow_reviews
  add constraint stockflow_reviews_etat_check
  check (etat in ('ok','no','diff'));

-- La lecture des revues est deja ouverte a tout utilisateur connecte
-- (policy sf_reviews_read), donc l'admin voit les differences des magasins
-- sans changement supplementaire.
