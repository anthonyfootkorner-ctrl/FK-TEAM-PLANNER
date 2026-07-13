# Dictionnaire et mapping des donnees — StockFlow AI

Livrable de l'**Etape 1 (cadrage des donnees)**. Ce document decrit les
fichiers d'entree attendus, leurs colonnes canoniques, les cles metier et les
alias reconnus automatiquement par le moteur (`stockflow/schema.py`).

Le moteur est **tolerant** sur les intitules (accents, casse, espaces,
underscores) mais **bloque** le traitement si une colonne *essentielle* manque.

## Cles metier

- **Ligne stock / vente / picking** : `magasin + reference + couleur + taille`
- **SKU** : `reference + couleur + taille`
- **Magasin** : identifie par son `code_magasin` et sa `ville`

## 1. Fichier stocks (`data/stocks/`)

| Colonne canonique | Obligatoire | Alias reconnus (exemples) |
|---|---|---|
| `magasin` | ✅ | boutique, store, depot, pdv, code_magasin |
| `ville` |  | city, commune |
| `reference` | ✅ | ref, article, modele, sku |
| `couleur` | ✅ | color, coloris |
| `taille` | ✅ | size, pointure |
| `stock_physique` | ✅ | stock, qte_stock, stock_reel |
| `stock_disponible` |  | dispo, stock_dispo (defaut = physique) |
| `categorie` |  | famille, rayon (pilote les tailles coeur) |
| `genre` |  | sexe |
| `marque` |  | brand |
| `prix_vente` |  | pv, prix_ttc |
| `prix_achat` |  | pa, cout_achat |
| `date_premiere_reception` |  | |
| `date_derniere_reception` |  | |
| `statut_reference` |  | etat_reference |
| `indic_web` |  | web, is_web |
| `indic_picking` |  | picking, is_picking |

## 2. Fichier ventes (`data/ventes/`)

| Colonne canonique | Obligatoire | Alias |
|---|---|---|
| `magasin` | ✅ | |
| `reference` | ✅ | |
| `couleur` | ✅ | |
| `taille` | ✅ | |
| `ventes_35j` | ✅ | ventes_35, vte_35j |
| `ventes_7j` |  | ventes_7, vte_7j |
| `ca_35j` |  | chiffre_affaires_35j |
| `ca_7j` |  | |
| `date_derniere_vente` |  | |

> Les ventes 35 jours sont la base du besoin ; les 7 jours servent a la
> tendance (hausse / stable / baisse).

## 3. Fichier reassorts Picking (`data/picking/`)

| Colonne canonique | Obligatoire | Alias |
|---|---|---|
| `magasin` (destinataire) | ✅ | |
| `reference` | ✅ | |
| `couleur` | ✅ | |
| `taille` | ✅ | |
| `quantite_prevue` | ✅ | qte_prevue |
| `date_preparation` |  | |
| `date_reception_prevue` |  | eta |
| `statut_reassort` |  | statut_picking |
| `id_mouvement` |  | id_mvt |

> **Seuls les reassorts non receptionnes** comptent comme stock en transit.
> Statuts consideres receptionnes : `receptionne, recu, livre, clos, termine…`
> Ils ne sont **jamais** doubles par le moteur (besoin residuel).

## 4. Fichier magasins (`data/magasins/`)

| Colonne canonique | Obligatoire | Alias |
|---|---|---|
| `code_magasin` | ✅ | code, id_magasin |
| `nom_magasin` |  | libelle, enseigne |
| `ville` | ✅ | |
| `region` |  | zone |
| `flagship` |  | is_flagship |
| `type_magasin` |  | format (valeur `WEB` => magasin Web) |
| `actif` |  | ouvert, is_active |
| `priorite` |  | |
| `capacite` |  | capacite_stockage |

## 5. Fichier historique des transferts (`data/historique/`)

| Colonne canonique | Obligatoire | Alias |
|---|---|---|
| `expediteur` | ✅ | source, origine |
| `destinataire` | ✅ | cible, destination |
| `reference` | ✅ | |
| `couleur` | ✅ | |
| `taille` | ✅ | |
| `quantite` |  | |
| `date_transfert` |  | |
| `statut` |  | |
| `date_reception` |  | |
| `resultat_vente` |  | ventes_apres |

> Sert a eviter les transferts en boucle / croises (delai de protection).

## 6. Fichier parametres (`config/parametres.xlsx`)

Feuille `parametres` (colonnes `cle`, `valeur`) + feuille `tailles_coeur`
(colonnes `categorie`, `taille_coeur`). Les valeurs complexes (listes,
dictionnaires) sont acceptees en JSON. Voir la doc technique pour la liste
complete des seuils.

## 7. Distances (optionnel, `config/distances.xlsx`)

Colonnes `ville_a`, `ville_b`, `km`. En son absence : 0 km si meme ville,
sinon `distance_defaut_km`. La distance influence le score sans etre bloquante.

## Detection du Web

Un magasin est considere « Web » si : son code figure dans le parametre
`magasins_web`, **ou** son `type_magasin` vaut `WEB`, **ou** son code contient
`WEB`. Le Web alimente tous les magasins, recoit reliquats et grilles
incompletes, et reste protege par sa couverture minimale.

## Donnees reelles (exports Fastmag) — adaptateur `ingest_real.py`

Les exports reels ne suivent pas exactement le modele theorique ci-dessus.
L'adaptateur les convertit automatiquement.

### STOCK (`STOCK_13.csv`) — grain magasin × marque × code-barre × taille

| Colonne export | Traitement |
|---|---|
| `Code_Origine` | -> `magasin` (et `ville` = code, referentiel minimal) |
| `Marque Gp` | -> `marque` |
| `BarCode V2` | -> `reference` (modele) + `couleur` (suffixe apres `-`) |
| `Taille` | -> `taille` standardisee + `categorie` = famille de taille |
| `PrixAchat` | -> `prix_achat` |
| `Total Stock` | -> `stock_physique` (doublons agreges) |

### VENTES (`VENTESTOCKFLOW.csv`) — grain magasin × code-barre × taille × jour

| Colonne export | Traitement |
|---|---|
| `Jours dans Date` | agregation 35 j (base) et 7 j (tendance) |
| `Code_Origine` | -> `magasin` |
| `BarCode V2` | -> `reference` + `couleur` |
| `Taille` | -> `taille` standardisee |
| `PrixVente` | -> enrichit `prix_vente` du stock (absent du fichier stock) |
| `Saison` | disponible pour les exclusions saison |
| `Total QteVenteRetail` | -> `ventes_35j` / `ventes_7j` |
| `Total MtVenteRetailTTC` | -> `ca_35j` / `ca_7j` |

### OBJECTIF (`OBJECTIF_4.csv`) — grain magasin × jour

Objectifs et trafic (tickets) par magasin ; réserve pour la criticité magasin.

### Points d'attention (exports reels)

- **Ruptures recuperees** : le fichier stock ne liste que du stock positif ; les
  tailles vendues mais en rupture (stock 0) sont recreees a 0 par l'adaptateur
  pour rester des cibles de reassort.
- **Tailles** : 728 variantes standardisees en familles (LETTRE / CHAUSSURE /
  ENFANT / AUTRE). La regle « 2 tailles coeur » ne s'applique qu'aux lettres
  adultes ; pour chaussures/enfant elle est neutre.
- **Fichiers manquants** : Picking, Magasins (ville/region/flagship) et
  Historique ne sont pas dans les exports fournis => regles associees neutres
  (mode degrade, reversible).
- **BarCode sans tiret** (~17%) : couleur = `UNI`.

## Controles de l'Etape 1

- aucune colonne essentielle manquante (sinon **blocage**) ;
- codes magasins et references non ambigus ;
- tailles standardisees (mises en majuscules) ;
- doublons agreges sur la cle de ligne ;
- distinction claire Web / Picking / magasins ;
- dates exploitables (parsing ISO puis jour-en-tete).
