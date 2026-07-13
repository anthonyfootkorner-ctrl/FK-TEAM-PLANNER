# Documentation technique — StockFlow AI

## Architecture

Le moteur est modulaire (`stockflow/`), un fichier par responsabilite, orchestre
par `pipeline.run_pipeline`. Aucune regle metier n'est codee en dur : tout seuil
provient de `parameters.Parameters` (defauts) ou de `config/parametres.xlsx`.

```
import_data ─┐
quality_checks ┤→ base propre
projected_stock → stock_actuel / stock_transit / stock_projete
sales_metrics   → moyenne_quotidienne, rythme_7j, tendance
coverage        → couverture_actuelle/projetee, besoin_residuel, surplus_donneur
size_grids      → GridIndex (etats de grille avant/apres, mutables)
store_criticality → Top N + indice de criticite magasin
donors / receivers → candidats donneurs et besoins receveurs
optimizer       → boucle iterative (scoring + contraintes)
simulation      → comparatif avant/apres
implantation    → propositions (jamais automatiques)
exports         → classeur Excel (7 onglets)
```

## Formules cle

- **Stock projete** = `stock_actuel + picking_en_transit + receptions_validees − sorties_programmees`
- **Moyenne quotidienne** = `ventes_35j / periode_ventes`
- **Couverture (jours)** = `stock_projete / moyenne_quotidienne`
  - stock = 0 → couverture = 0
  - stock > 0 et aucune vente → couverture = 999 (dormant)
- **Besoin residuel** = `max(0, ceil(cible × daily) − stock_projete)`
  (integre le Picking, donc **anti-double reassort**)
- **Surplus donneur** = `max(0, stock_actuel − ceil(couverture_min × daily))`
- **Tendance** : `variation = (rythme_7j − daily) / daily` ; hausse si
  `≥ seuil_tendance_hausse`, baisse si `≤ seuil_tendance_baisse`.

## Scoring (module 9)

Score sur 100 = somme ponderee de composantes normalisees (0–1), poids dans
`poids_scoring`, plus un bonus flagship additif borne. Composantes :
gain de couverture receveur, reduction de surstock donneur, amelioration de
grille, tailles coeur, potentiel de vente, tendance 7j, risque de rupture,
priorite Top 30, flagship, distance, regroupement logistique, penalite
d'historique. Classement : ≥90 prioritaire, ≥80 fortement recommande, ≥70
recommande, ≥60 a valider, <60 non retenu.

## Regles anti-erreur (module 5) — ou elles sont appliquees

| Regle | Implementation |
|---|---|
| Anti-double reassort | `coverage.besoin_residuel` net du Picking |
| Anti-transfert croise | `optimizer.pairs_open` + `hist_pairs` |
| Anti-transfert en chaine | `delai_protection_jours` + `received_lines` |
| Anti-casse de grille | `GridIndex.state_after_*` cote donneur ET receveur |
| Anti-surstock | besoin borne a la couverture cible |
| Anti-surutilisation Web | `couverture_min_web` dans `_cessible` |
| Anti-boucle | `max_iterations`, pas de stock negatif, blocages traces |
| Max 4 destinations | `optimizer.dest_used` |

## Moteur d'optimisation (module 10)

Boucle : generer les candidats (besoins × donneurs du meme SKU) → scorer →
retenir le meilleur ≥ seuil → mettre a jour stocks/grilles/destinations →
recommencer. Arret quand plus aucun candidat ne depasse le seuil, ou
`max_iterations`. La quantite d'un transfert = `min(besoin_restant, cessible)`,
le donneur conservant toujours sa couverture minimale.

## Reproductibilite

Aucune source d'aleatoire dans le moteur : memes fichiers + memes parametres →
memes resultats (teste par `test_reproductibilite`). Les parametres utilises
sont copies dans l'onglet **6-Parametres** et le **7-Journal**. Les exports
sont dates.

## Journalisation

`logs/stockflow.log` (fichier + console) et onglet **7-Journal** :
date, fichiers charges, nombre de lignes, anomalies, iterations, transferts
retenus, duree, version du moteur, parametres cles.

## Tests

`tests/` (pytest) : parametres, mapping/import, controle qualite, calculs
(echantillon controle, 100% concordance), grilles, contraintes de l'optimiseur,
conservation du stock, reproductibilite, blocage sur donnees incoherentes.

## Extension vers la V2

Points d'entree pensés pour l'evolution : connecteurs Fastmag/EGO (remplacer
`import_data`), previsions/saisonnalite (enrichir `sales_metrics`), execution
semi-automatique (consommer `exports`), optimisation transport (affiner
`geo` + `transfer_scoring`).
