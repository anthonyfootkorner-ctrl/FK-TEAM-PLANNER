# Guide utilisateur — StockFlow AI

## A quoi sert l'outil

StockFlow AI vous propose chaque semaine une liste de **transferts recommandes**
pour mieux repartir le stock entre vos magasins et le Web. Il **ne declenche
rien tout seul** : vous gardez la main sur chaque decision.

## 1. Preparer les fichiers

Deposez vos exports Excel dans les dossiers correspondants :

- `data/stocks/` — le stock par magasin / reference / couleur / taille ;
- `data/ventes/` — les ventes 35 jours et 7 jours ;
- `data/picking/` — les reassorts Picking deja programmes ;
- `data/magasins/` — la liste des magasins avec leur ville ;
- `data/historique/` — l'historique des transferts (optionnel mais conseille).

Les intitules de colonnes peuvent varier : l'outil reconnait les variantes
courantes. En cas de colonne essentielle manquante, il **s'arrete et vous
l'indique** (onglet 5 et journal).

## 2. Lancer une simulation

```bash
python main.py --config config/parametres.xlsx
```

Pour un essai sans donnees reelles : `python main.py --demo`.

Le resultat est un classeur Excel dans `exports/`, date du jour.

## 3. Lire le classeur (7 onglets)

1. **Transferts** — la liste a valider : priorite, score, expediteur,
   destinataire, reference/couleur/taille, quantite, stock et couverture
   avant/apres, grille avant/apres, **motif** de chaque transfert, distance.
2. **Synthese flux** — un resume par couple expediteur → destinataire (nombre
   de references, pieces, valeur, colis estimes).
3. **Simulation** — l'impact avant / apres (ruptures, couvertures, grilles,
   score de sante reseau, valeur deplacee).
4. **Implantations** — des idees de nouvelles references a implanter (pour
   decision humaine, jamais automatiques).
5. **Cas non traites** — ce que l'outil n'a pas pu faire et pourquoi (besoin
   sans donneur, blocage de grille, limite de 4 destinations, anomalies…).
6. **Parametres** — tous les seuils utilises pour cette execution.
7. **Journal** — la trace de l'execution (fichiers, iterations, duree…).

Les onglets 8 et 9 donnent le **Top references** et l'**indice de criticite**
par magasin.

## 4. Comprendre une recommandation

Chaque ligne de l'onglet Transferts porte une **priorite** (couleur) et un
**motif** en clair, par exemple :

> *couvre un risque de rupture (3j) ; ameliore la grille (S/XL → S/M/XL) ;
> reference du Top 30 magasin ; degage un surstock donneur*

Un score eleve = un transfert a fort impact commercial. En dessous de 60, le
transfert n'est pas propose.

## 5. Ajuster les regles

Ouvrez `config/parametres.xlsx` (feuille `parametres`) pour modifier les seuils
sans toucher au code, par exemple :

| Pour… | Modifiez |
|---|---|
| viser plus de stock en magasin | `couverture_cible_magasin` |
| proteger davantage les expediteurs | `couverture_min_expediteur` |
| proteger le Web | `couverture_min_web` |
| autoriser plus de destinations | `nb_max_destinations` |
| etre plus/moins selectif | `seuil_score_minimum` |
| exclure une marque / reference | `exclusions_marque`, `exclusions_reference` |

Relancez ensuite une simulation : les memes fichiers avec les memes parametres
donnent toujours le meme resultat.

## 6. Bonnes pratiques du pilote

- commencez sur 5 a 10 magasins et une categorie ;
- validez les transferts avec les equipes avant execution ;
- mesurez les ventes a 7 / 14 / 30 jours apres transfert ;
- remontez les incoherences (onglet 5) pour affiner les regles.
