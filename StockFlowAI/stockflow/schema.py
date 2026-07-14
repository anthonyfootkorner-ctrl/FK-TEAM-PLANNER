"""Schema canonique des donnees et mapping des colonnes.

Les exports reels (Fastmag, EGO, ...) n'ont jamais exactement les memes
intitules de colonnes. Ce module definit :

* les noms de colonnes *canoniques* utilises dans tout le moteur ;
* un dictionnaire d'alias pour reconnaitre les intitules courants ;
* les colonnes obligatoires par type de fichier (pour les controles qualite).

Le mapping est volontairement tolerant (accents, casse, espaces, underscores)
mais il ne devine jamais une colonne essentielle manquante : c'est le role du
module :mod:`stockflow.quality_checks` de bloquer le traitement dans ce cas.
"""

from __future__ import annotations

import unicodedata
from typing import Dict, List

import pandas as pd


# --- cles metier ------------------------------------------------------------
SKU_KEYS = ["reference", "couleur", "taille"]
LINE_KEYS = ["magasin", "reference", "couleur", "taille"]


# --- colonnes canoniques par fichier ---------------------------------------
STOCK_COLUMNS = [
    "magasin", "ville", "reference", "couleur", "taille",
    "stock_physique", "stock_disponible", "categorie", "genre", "marque",
    "prix_vente", "prix_achat", "date_premiere_reception",
    "date_derniere_reception", "statut_reference", "indic_web", "indic_picking",
]
STOCK_REQUIRED = ["magasin", "reference", "couleur", "taille", "stock_physique"]

SALES_COLUMNS = [
    "magasin", "reference", "couleur", "taille",
    "ventes_35j", "ventes_7j", "ca_35j", "ca_7j", "date_derniere_vente",
]
SALES_REQUIRED = ["magasin", "reference", "couleur", "taille", "ventes_35j"]

PICKING_COLUMNS = [
    "magasin", "reference", "couleur", "taille", "quantite_prevue",
    "date_preparation", "date_reception_prevue", "statut_reassort", "id_mouvement",
]
PICKING_REQUIRED = ["magasin", "reference", "couleur", "taille", "quantite_prevue"]

STORE_COLUMNS = [
    "code_magasin", "nom_magasin", "ville", "region", "flagship",
    "type_magasin", "actif", "priorite", "capacite",
]
STORE_REQUIRED = ["code_magasin", "ville"]

HISTORY_COLUMNS = [
    "expediteur", "destinataire", "reference", "couleur", "taille",
    "quantite", "date_transfert", "statut", "date_reception", "resultat_vente",
]
HISTORY_REQUIRED = ["expediteur", "destinataire", "reference", "couleur", "taille"]


# --- alias : canonique -> variantes reconnues ------------------------------
ALIASES: Dict[str, List[str]] = {
    "magasin": ["magasin", "boutique", "store", "depot", "point_de_vente", "pdv", "mag"],
    "ville": ["ville", "city", "commune"],
    "reference": ["reference", "ref", "article", "modele", "code_article", "sku", "produit"],
    "couleur": ["couleur", "color", "coloris"],
    "taille": ["taille", "size", "pointure"],
    "stock_physique": ["stock_physique", "stock", "qte_stock", "quantite_stock", "stock_theorique", "stock_reel"],
    "stock_disponible": ["stock_disponible", "dispo", "disponible", "stock_dispo", "qte_dispo"],
    "categorie": ["categorie", "category", "famille", "rayon"],
    "genre": ["genre", "sexe", "gender"],
    "marque": ["marque", "brand"],
    "prix_vente": ["prix_vente", "pv", "prix_de_vente", "prix_ttc", "prix"],
    "prix_achat": ["prix_achat", "pa", "prix_de_revient", "cout", "cout_achat"],
    "date_premiere_reception": ["date_premiere_reception", "premiere_reception", "date_1ere_reception", "date_creation"],
    "date_derniere_reception": ["date_derniere_reception", "derniere_reception", "date_der_reception"],
    "statut_reference": ["statut_reference", "statut", "statut_article", "etat_reference"],
    "indic_web": ["indic_web", "web", "is_web", "flag_web", "indicateur_web"],
    "indic_picking": ["indic_picking", "picking", "is_picking", "flag_picking", "indicateur_picking"],
    # ventes
    "ventes_35j": ["ventes_35j", "ventes_35", "ventes35", "qte_vendue_35j", "ventes_35_jours", "vte_35j"],
    "ventes_7j": ["ventes_7j", "ventes_7", "ventes7", "qte_vendue_7j", "ventes_7_jours", "vte_7j"],
    "ca_35j": ["ca_35j", "ca35", "chiffre_affaires_35j", "ca_35_jours", "ca_35"],
    "ca_7j": ["ca_7j", "ca7", "chiffre_affaires_7j", "ca_7_jours", "ca_7"],
    "date_derniere_vente": ["date_derniere_vente", "derniere_vente", "date_der_vente", "last_sale"],
    # picking
    "quantite_prevue": ["quantite_prevue", "qte_prevue", "quantite", "qte", "quantite_reassort"],
    "date_preparation": ["date_preparation", "date_prepa", "prepared_at"],
    "date_reception_prevue": ["date_reception_prevue", "date_reception", "date_prevue_reception", "eta"],
    "statut_reassort": ["statut_reassort", "statut_picking", "etat_reassort", "statut_mouvement"],
    "id_mouvement": ["id_mouvement", "id", "id_mvt", "mouvement", "num_mouvement"],
    # magasins
    "code_magasin": ["code_magasin", "code_mag", "id_magasin"],
    "nom_magasin": ["nom_magasin", "nom", "libelle", "name", "enseigne"],
    "region": ["region", "zone", "secteur"],
    "flagship": ["flagship", "is_flagship", "vaisseau_amiral", "flag"],
    "type_magasin": ["type_magasin", "type", "format"],
    "actif": ["actif", "active", "ouvert", "statut_magasin", "is_active"],
    "priorite": ["priorite", "priority", "poids"],
    "capacite": ["capacite", "capacity", "capacite_stockage"],
    # historique
    "expediteur": ["expediteur", "source", "from", "magasin_source", "emetteur", "origine"],
    "destinataire": ["destinataire", "cible", "to", "magasin_cible", "destination"],
    "date_transfert": ["date_transfert", "date_envoi", "date"],
    "date_reception": ["date_reception", "recu_le", "received_at"],
    "resultat_vente": ["resultat_vente", "ventes_apres", "vente_post_transfert"],
}


def _norm(text: str) -> str:
    """Normalise un intitule : minuscules, sans accents, underscores."""
    s = unicodedata.normalize("NFKD", str(text))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.strip().lower()
    for ch in (" ", "-", "/", ".", "'", "(", ")", "\n", "\t"):
        s = s.replace(ch, "_")
    while "__" in s:
        s = s.replace("__", "_")
    return s.strip("_")


# alias inverse pre-calcule : variante normalisee -> canonique
_REVERSE: Dict[str, str] = {}
for _canon, _variants in ALIASES.items():
    for _v in _variants:
        _REVERSE[_norm(_v)] = _canon
    _REVERSE.setdefault(_norm(_canon), _canon)


def map_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Renomme les colonnes d'un DataFrame vers les noms canoniques connus.

    Les colonnes inconnues sont conservees (normalisees) : elles peuvent servir
    a l'utilisateur sans perturber le moteur.
    """
    rename: Dict[str, str] = {}
    seen: set[str] = set()
    for col in df.columns:
        norm = _norm(col)
        canon = _REVERSE.get(norm, norm)
        # eviter les collisions (2 colonnes mappees vers le meme canonique)
        if canon in seen:
            canon = f"{canon}__dup"
        seen.add(canon)
        rename[col] = canon
    return df.rename(columns=rename)


def missing_required(df: pd.DataFrame, required: List[str]) -> List[str]:
    """Liste les colonnes obligatoires absentes apres mapping."""
    return [c for c in required if c not in df.columns]
