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

### Sur les exports reels (Fastmag)

Les exports reels (STOCK, VENTESTOCKFLOW, OBJECTIF) ont un format different du
modele theorique. L'adaptateur `stockflow/ingest_real.py` les transforme sans
toucher au moteur :

```bash
python run_real.py --stock STOCK.csv --ventes VENTESTOCKFLOW.csv \
                   --objectif OBJECTIF.csv --today 2026-07-13
```

Choix d'adaptation (reversibles, a valider avec le metier) :
- `reference` = **code-barre complet** (`BarCode V2` non decoupe : un code-barre
  = un produit, retrouvable tel quel dans le systeme source) ;
- tailles standardisees en familles (LETTRE / CHAUSSURE / ENFANT) qui pilotent
  les tailles coeur ;
- `prix_vente` recupere depuis le fichier de ventes ;
- **recuperation des ruptures** : les tailles vendues mais en stock 0 (absentes
  du fichier stock) sont materialisees pour redevenir des cibles de reassort ;
- referentiel magasins minimal deduit des codes (ville = code, `WEB` detecte) ;
- Picking / historique absents => regles associees neutres jusqu'a fourniture.

Sur le jeu reel fourni (89 magasins, 305k lignes stock, 35 j de ventes) :
ruptures **-3 982**, stock dormant **-7 181**, couverture moyenne **+3,2 j**,
score de sante reseau **+5,2**, stock total conserve, calcul ~2 min. Voir
`documentation/mapping_donnees.md` (section « Donnees reelles »).

## Mini-site local (glisser-deposer)

Pour lancer StockFlow AI sans ligne de commande :

- **Windows** : double-cliquez `lancer_stockflow.bat`
- **macOS / Linux** : double-cliquez `lancer_stockflow.command`
  (Mac, 1re fois : clic droit > Ouvrir)

Une page s'ouvre dans le navigateur : deposez vos fichiers (STOCK, VENTES, et si
disponibles REASSORT / OBJECTIF), reglez la cible de couverture, cliquez sur
**Lancer l'analyse**, consultez les indicateurs avant/apres et telechargez
l'Excel complet. Equivalent manuel :

```bash
pip install -r requirements.txt
streamlit run app.py
```

Le moteur est strictement le meme qu'en ligne de commande — l'appli n'est que
l'habillage (voir `app.py` / `stockflow/app_service.py`).

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
