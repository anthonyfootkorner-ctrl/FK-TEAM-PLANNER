# StockFlow AI — V1

Moteur d'aide a la decision pour la repartition des stocks (Picking, Web,
magasins, receptions programmees). Il **recommande** des transferts fiables,
explicables et validables — il n'execute **aucun** mouvement automatiquement.

> Conforme au brief de developpement StockFlow AI (perimetre V1).

## Ce que fait la V1

- importe les fichiers Excel (stocks, ventes, picking, magasins, historique) ;
- controle leur qualite et **bloque** si une donnee essentielle manque ;
- integre les reassorts Picking en transit (stock projete) ;
- calcule ventes, tendances, couvertures et **besoin residuel** ;
- analyse les grilles de tailles (tailles coeur) ;
- identifie donneurs et receveurs ;
- score chaque transfert candidat sur 100 avec un **motif lisible** ;
- optimise le reseau par iterations (max 4 destinations / expediteur, anti
  double reassort, anti croise, anti chaine, anti casse de grille, protection
  du Web) ;
- simule l'impact avant / apres ;
- exporte un classeur Excel complet (7 onglets + top references + criticite).

La connexion automatique a Fastmag / EGO **ne fait pas partie de la V1**.

## Installation

```bash
cd StockFlowAI
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Utilisation

```bash
# Demonstration de bout en bout (genere un jeu de donnees fictif) :
python main.py --demo

# Sur vos donnees reelles (deposez les .xlsx dans data/<type>/) :
python main.py --config config/parametres.xlsx

# Options :
python main.py --stocks data/stocks --ventes data/ventes \
               --picking data/picking --magasins data/magasins \
               --historique data/historique \
               --today 2026-07-13 --export exports/resultat.xlsx
```

L'export est genere dans `exports/` et date. Le journal d'execution est ecrit
dans `logs/stockflow.log` et dans l'onglet **7-Journal** du classeur.

## Structure

```
StockFlowAI/
├── config/            parametres.xlsx, tailles_coeur.xlsx (seuils modifiables)
├── data/              fichiers d'entree (stocks / ventes / picking / magasins / historique)
├── stockflow/         modules du moteur (1 fichier = 1 responsabilite)
├── tests/             tests unitaires (pytest)
├── exports/           classeurs Excel dates
├── logs/              journal d'execution
├── documentation/     mapping des donnees, doc technique, guide utilisateur
└── main.py            point d'entree
```

## Modules du moteur (`stockflow/`)

| Fichier | Role (brief) |
|---|---|
| `parameters.py` | parametres externes — **aucune regle codee en dur** |
| `schema.py` | schema canonique + mapping des colonnes reelles |
| `import_data.py` | Module 1 — import et standardisation |
| `quality_checks.py` | Module 1 — controle qualite, rapport d'anomalies |
| `projected_stock.py` | Module 2 — stock projete (Picking en transit) |
| `sales_metrics.py` | Module 3 — ventes, rythmes, tendances |
| `coverage.py` | Module 3 — couvertures et besoin residuel |
| `size_grids.py` | Module 4 — grilles de tailles (avant/apres) |
| `donors.py` | Module 5 — detection des donneurs |
| `receivers.py` | Module 6 — detection des receveurs |
| `store_criticality.py` | Modules 7 & 8 — Top 30 et indice de criticite |
| `transfer_scoring.py` | Module 9 — scoring des transferts |
| `optimizer.py` | Module 10 — moteur d'optimisation iteratif |
| `simulation.py` | comparatif avant / apres |
| `implantation.py` | propositions d'implantation (jamais automatiques) |
| `exports.py` | generation du classeur Excel (7 onglets) |
| `pipeline.py` | orchestration de bout en bout |

## Tests

```bash
python -m pytest -q
```

## Parametres cles (modifiables dans `config/parametres.xlsx`)

| Parametre | Defaut | Sens |
|---|---|---|
| `couverture_cible_magasin` | 30 j | cible receveur apres reassort |
| `couverture_min_expediteur` | 20 j | a conserver apres transfert |
| `couverture_min_web` | 30 j | reserve Web protegee |
| `nb_max_destinations` | 4 | destinations / expediteur / semaine |
| `min_tailles_coeur_receveur` | 2 | tailles coeur mini (ex. 2 parmi S/M/L) |
| `seuil_score_minimum` | 60 | score minimal pour retenir un transfert |
| `delai_protection_jours` | 21 | anti chaine / anti boucle apres reception |

Voir `documentation/` pour le detail complet.
