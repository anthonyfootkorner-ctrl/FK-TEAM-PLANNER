-- ============================================================================
--  STOCKFLOW.AI — Effacer les anciens transferts (données de test)
--  A coller dans Supabase > SQL Editor, puis « Run ».
--
--  Supprimer un run efface EN CASCADE tout ce qui lui est rattaché :
--  transferts, réassort central, donneurs, valorisation, revues, expéditions.
--  Les comptes utilisateurs et l'association magasins ne sont PAS touchés.
-- ============================================================================


-- ▶ OPTION 1 (recommandée avant la mise en route) — TOUT effacer, repartir de zéro
delete from public.stockflow_runs;

-- Remettre à zéro le total valorisé « depuis le début » (sinon il garde les
-- montants générés par les runs de test). À garder pour un vrai départ propre.
update public.stockflow_valo_total set units = 0, ca = 0, marge = 0, updated_at = now();


-- ─────────────────────────────────────────────────────────────────────────────
-- ▶ OPTION 2 (alternative) — garder UNIQUEMENT le dernier run, effacer les autres
--   Décommente les 2 lignes ci-dessous et NE lance PAS l'option 1.
--
-- delete from public.stockflow_runs
--   where id <> (select id from public.stockflow_runs order by created_at desc limit 1);


-- ─────────────────────────────────────────────────────────────────────────────
-- ▶ OPTIONNEL — effacer aussi les demandes urgentes de test (dépannage magasin)
--   Décommente si tu veux repartir sans aucune demande en cours.
--
-- delete from public.stockflow_urgent_requests;
-- ============================================================================
