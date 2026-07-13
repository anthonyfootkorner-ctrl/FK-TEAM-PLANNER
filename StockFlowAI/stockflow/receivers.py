"""Module 6 - Detection des receveurs.

Genere la liste des *besoins* receveur au niveau
(magasin, reference, couleur, taille). Deux natures de besoin :

* ``couverture`` : la ligne se vend et sa couverture projetee est sous la cible
  (besoin residuel apres Picking) ;
* ``grille``     : la reference est implantee mais une taille coeur manque, et
  la completer ameliorerait clairement la grille.

Regles respectees :
* uniquement des references DEJA implantees dans le magasin receveur (2.8) ;
* le Picking deja programme ne doit pas etre double (besoin residuel, 5.1) ;
* le Web n'est pas un receveur du flux principal (il recoit des reliquats,
  traite a part).
"""

from __future__ import annotations

from typing import Set

import numpy as np
import pandas as pd

from .parameters import Parameters
from .size_grids import GridIndex


def detect_receivers(df: pd.DataFrame, index: GridIndex, params: Parameters,
                     web_codes: Set[str]) -> pd.DataFrame:
    """Renvoie la table des besoins receveur (une ligne par besoin)."""
    cible = float(params.get("couverture_cible_magasin", 30))
    is_web = df["is_web"] if "is_web" in df else df["magasin"].astype(str).str.upper().isin(web_codes)
    physiques = df[~is_web].copy()
    # magasins exclus des flux (reserve externe, ex. CENTRAL) : pas receveurs
    exclus_flux = {str(x).strip().upper() for x in params.get("magasins_exclus_flux", []) or []}
    if exclus_flux:
        physiques = physiques[~physiques["magasin"].astype(str).str.upper().isin(exclus_flux)]

    besoins = []

    # 1) Besoins de couverture sur les lignes existantes
    for row in physiques.itertuples(index=False):
        besoin = float(getattr(row, "besoin_residuel", 0) or 0)
        cov = float(getattr(row, "couverture_projetee", 0) or 0)
        tendance = getattr(row, "tendance", "stable")
        daily = float(getattr(row, "moyenne_quotidienne", 0) or 0)
        actif = daily > 0
        risque = cov < 7  # rupture sous 7 jours
        # ventes actives + tendance non baissiere, OU risque de rupture avere
        eligible = besoin >= 1 and cov < cible and (
            (actif and tendance in ("stable", "hausse")) or risque
        )
        if eligible:
            besoins.append(_need_row(row, taille=str(row.taille),
                                     qte=besoin, type_besoin="couverture",
                                     motif=_motif_couverture(cov, tendance, risque)))

    # 2) Besoins de grille : taille coeur manquante sur une reference implantee
    #    On parcourt chaque (magasin, reference, couleur) physique implante.
    #    IMPORTANT : on ne complete la grille que pour des references REELLEMENT
    #    vendues dans le magasin (ventes actives), sinon on gonflerait le stock
    #    dormant des magasins sans rotation.
    ventes_grp = (
        physiques.groupby(["magasin", "reference", "couleur"])["moyenne_quotidienne"]
        .sum()
    )
    seen = set()
    for row in physiques.itertuples(index=False):
        key = (str(row.magasin), str(row.reference), str(row.couleur))
        if key in seen:
            continue
        seen.add(key)
        if float(ventes_grp.get(key, 0.0)) <= 0:
            continue  # reference sans vente dans ce magasin -> pas de completion
        state = index.state(*key)
        core = [c.upper() for c in index.core_sizes(str(row.reference), str(row.couleur))]
        present = {t.upper() for t in state.tailles_dispo}
        manquantes = [c for c in core if c not in present]
        # ne proposer que si completer permet d'atteindre le minimum de tailles coeur
        if manquantes and state.nb_coeur < int(params.get("min_tailles_coeur_receveur", 2)):
            for taille in manquantes:
                besoins.append(_need_row(row, taille=taille, qte=2.0,
                                         type_besoin="grille",
                                         motif=f"Taille coeur {taille} absente (grille {state.label()})"))

    if not besoins:
        return pd.DataFrame(columns=_NEED_COLUMNS)
    out = pd.DataFrame(besoins)
    # dedoublonnage (une meme taille peut apparaitre 2x) : garde le besoin max
    out = (out.sort_values("qte_besoin", ascending=False)
              .drop_duplicates(subset=["magasin", "reference", "couleur", "taille"], keep="first")
              .reset_index(drop=True))
    return out


_NEED_COLUMNS = [
    "magasin", "ville", "reference", "couleur", "taille", "categorie",
    "qte_besoin", "couverture_projetee", "moyenne_quotidienne", "tendance",
    "type_besoin", "motif_besoin",
]


def _need_row(row, taille: str, qte: float, type_besoin: str, motif: str) -> dict:
    return {
        "magasin": str(row.magasin),
        "ville": getattr(row, "ville", None),
        "reference": str(row.reference),
        "couleur": str(row.couleur),
        "taille": str(taille),
        "categorie": getattr(row, "categorie", None),
        "qte_besoin": float(qte),
        "couverture_projetee": float(getattr(row, "couverture_projetee", 0) or 0),
        "moyenne_quotidienne": float(getattr(row, "moyenne_quotidienne", 0) or 0),
        "tendance": getattr(row, "tendance", "stable"),
        "type_besoin": type_besoin,
        "motif_besoin": motif,
    }


def _motif_couverture(cov: float, tendance: str, risque: bool) -> str:
    if risque:
        return f"Risque de rupture (couverture {cov:.0f}j)"
    return f"Couverture {cov:.0f}j sous la cible, tendance {tendance}"
