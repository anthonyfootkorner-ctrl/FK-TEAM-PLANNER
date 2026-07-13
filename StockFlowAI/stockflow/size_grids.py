"""Module 4 - Analyse des grilles de tailles.

Pour chaque (magasin, reference, couleur) on evalue la grille :
tailles disponibles, tailles coeur presentes, qualite de grille, validite.

On expose un :class:`GridIndex` qui permet de simuler efficacement l'etat
d'une grille avant / apres un transfert (sans recalculer tout le DataFrame),
ce dont le moteur d'optimisation a besoin a chaque iteration.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

import pandas as pd

from .parameters import Parameters


GridKey = Tuple[str, str, str]  # (magasin, reference, couleur)


@dataclass
class GridState:
    tailles_dispo: List[str]
    tailles_coeur: List[str]
    nb_coeur: int
    nb_tailles: int
    qualite: float
    valide: bool

    def label(self) -> str:
        return "/".join(self.tailles_dispo) if self.tailles_dispo else "-"


class GridIndex:
    """Index mutable des stocks par (magasin, reference, couleur) -> {taille: stock}."""

    def __init__(self, params: Parameters):
        self.params = params
        self.min_coeur = int(params.get("min_tailles_coeur_receveur", 2))
        # (mag, ref, coul) -> {taille: stock}
        self._grids: Dict[GridKey, Dict[str, float]] = {}
        # (ref, coul) -> categorie (pour les tailles coeur)
        self._categorie: Dict[Tuple[str, str], str] = {}
        # (ref, coul) -> set des tailles existant dans le reseau
        self._network_sizes: Dict[Tuple[str, str], set] = {}

    @classmethod
    def from_frame(cls, df: pd.DataFrame, params: Parameters,
                   stock_col: str = "stock_actuel") -> "GridIndex":
        idx = cls(params)
        for row in df.itertuples(index=False):
            mag = str(getattr(row, "magasin"))
            ref = str(getattr(row, "reference"))
            coul = str(getattr(row, "couleur"))
            taille = str(getattr(row, "taille"))
            stock = float(getattr(row, stock_col, 0) or 0)
            key = (mag, ref, coul)
            idx._grids.setdefault(key, {})[taille] = idx._grids.get(key, {}).get(taille, 0.0) + stock
            cat = getattr(row, "categorie", None)
            idx._categorie.setdefault((ref, coul), str(cat) if cat is not None else None)
            idx._network_sizes.setdefault((ref, coul), set()).add(taille)
        return idx

    # -- acces ---------------------------------------------------------------
    def stock(self, mag: str, ref: str, coul: str, taille: str) -> float:
        return self._grids.get((mag, ref, coul), {}).get(taille, 0.0)

    def categorie(self, ref: str, coul: str) -> str | None:
        return self._categorie.get((ref, coul))

    def core_sizes(self, ref: str, coul: str) -> List[str]:
        return self.params.tailles_coeur_for(self.categorie(ref, coul))

    # -- etats ---------------------------------------------------------------
    def _state_from_sizes(self, sizes: Dict[str, float], ref: str, coul: str) -> GridState:
        core = [s.upper() for s in self.core_sizes(ref, coul)]
        dispo = sorted([t for t, q in sizes.items() if q > 0])
        coeur_dispo = [t for t in dispo if t.upper() in core]
        nb_coeur = len(coeur_dispo)
        nb_tailles = len(dispo)
        denom_core = max(1, len(core))
        # qualite : 70% couverture coeur + 30% largeur de gamme
        network = self._network_sizes.get((ref, coul), set(dispo))
        largeur = nb_tailles / max(1, len(network))
        qualite = round(0.7 * (nb_coeur / denom_core) + 0.3 * largeur, 3)
        valide = nb_coeur >= self.min_coeur
        return GridState(dispo, coeur_dispo, nb_coeur, nb_tailles, qualite, valide)

    def state(self, mag: str, ref: str, coul: str) -> GridState:
        return self._state_from_sizes(self._grids.get((mag, ref, coul), {}), ref, coul)

    def state_after_add(self, mag: str, ref: str, coul: str, taille: str,
                        qty: float) -> GridState:
        sizes = dict(self._grids.get((mag, ref, coul), {}))
        sizes[taille] = sizes.get(taille, 0.0) + qty
        return self._state_from_sizes(sizes, ref, coul)

    def state_after_remove(self, mag: str, ref: str, coul: str, taille: str,
                           qty: float) -> GridState:
        sizes = dict(self._grids.get((mag, ref, coul), {}))
        sizes[taille] = max(0.0, sizes.get(taille, 0.0) - qty)
        return self._state_from_sizes(sizes, ref, coul)

    # -- mutation (utilise par l'optimiseur apres validation d'un transfert) --
    def apply_move(self, expediteur: str, destinataire: str, ref: str, coul: str,
                   taille: str, qty: float) -> None:
        src = self._grids.setdefault((expediteur, ref, coul), {})
        src[taille] = max(0.0, src.get(taille, 0.0) - qty)
        dst = self._grids.setdefault((destinataire, ref, coul), {})
        dst[taille] = dst.get(taille, 0.0) + qty
        self._network_sizes.setdefault((ref, coul), set()).add(taille)


def annotate_grids(df: pd.DataFrame, index: GridIndex) -> pd.DataFrame:
    """Ajoute au DataFrame la qualite/validite de grille au niveau ref+couleur."""
    df = df.copy()
    qualites, valides, nb_coeur, grille_lbl = [], [], [], []
    cache: Dict[GridKey, GridState] = {}
    for row in df.itertuples(index=False):
        key = (str(row.magasin), str(row.reference), str(row.couleur))
        if key not in cache:
            cache[key] = index.state(*key)
        st = cache[key]
        qualites.append(st.qualite)
        valides.append(st.valide)
        nb_coeur.append(st.nb_coeur)
        grille_lbl.append(st.label())
    df["grille_qualite"] = qualites
    df["grille_valide"] = valides
    df["grille_nb_coeur"] = nb_coeur
    df["grille_tailles"] = grille_lbl
    return df
