"""Utilitaire de proximite geographique.

Les magasins sont identifies par leur ville (brief 2.10). La distance influence
le score sans etre bloquante :
* meme ville            -> 0 km ;
* villes differentes    -> matrice fournie si disponible, sinon distance par
  defaut (parametre ``distance_defaut_km``).

Une matrice optionnelle ``config/distances.xlsx`` (colonnes ville_a, ville_b,
km) peut etre fournie pour affiner. En son absence le moteur reste fonctionnel.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional, Tuple

import pandas as pd

from .parameters import Parameters


class DistanceMatrix:
    def __init__(self, params: Parameters, matrix: Optional[Dict[Tuple[str, str], float]] = None):
        self.params = params
        self.default = float(params.get("distance_defaut_km", 150))
        self._matrix = matrix or {}

    @classmethod
    def load(cls, params: Parameters, path: str | Path | None = None) -> "DistanceMatrix":
        matrix: Dict[Tuple[str, str], float] = {}
        if path is not None:
            p = Path(path)
            if p.exists():
                try:
                    df = pd.read_excel(p)
                    df.columns = [str(c).strip().lower() for c in df.columns]
                    if {"ville_a", "ville_b", "km"}.issubset(df.columns):
                        for _, r in df.iterrows():
                            a = str(r["ville_a"]).strip().lower()
                            b = str(r["ville_b"]).strip().lower()
                            km = float(r["km"])
                            matrix[(a, b)] = km
                            matrix[(b, a)] = km
                except Exception:
                    pass
        return cls(params, matrix)

    def km(self, ville_a: Optional[str], ville_b: Optional[str]) -> float:
        a = (str(ville_a).strip().lower() if ville_a is not None else "")
        b = (str(ville_b).strip().lower() if ville_b is not None else "")
        if not a or not b or a in ("nan", "none") or b in ("nan", "none"):
            return self.default
        if a == b:
            return 0.0
        return self._matrix.get((a, b), self.default)
