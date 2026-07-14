"""Module implantation - Propositions d'implantation (onglet separe).

Les reassorts automatiques ne concernent que des references DEJA implantees
(brief 2.8). Les nouvelles implantations ne sont jamais generees ni executees
automatiquement : elles sont seulement proposees, avec une justification, pour
decision humaine.

Une proposition est retenue si, pour un magasin ne detenant pas la reference :
* la reference se vend bien dans des magasins comparables (meme region/type) ;
* du stock reseau est disponible pour l'alimenter ;
* le score depasse ``seuil_proposition_implantation``.
"""

from __future__ import annotations

from typing import Dict, Set

import numpy as np
import pandas as pd

from .parameters import Parameters


def propose_implantations(base: pd.DataFrame, stores: pd.DataFrame,
                          params: Parameters, web_codes: Set[str]) -> pd.DataFrame:
    seuil = float(params.get("seuil_proposition_implantation", 70))
    is_web = base["magasin"].astype(str).str.upper().isin(web_codes)
    phys = base[~is_web].copy()
    if phys.empty:
        return pd.DataFrame(columns=_COLUMNS)

    # references presentes par magasin
    present: Set = set(zip(phys["magasin"].astype(str), phys["reference"].astype(str)))

    # performance moyenne d'une reference (rythme quotidien la ou elle est vendue)
    ref_perf = (
        phys[phys["moyenne_quotidienne"] > 0]
        .groupby("reference", as_index=False)
        .agg(daily_moyen=("moyenne_quotidienne", "mean"),
             nb_magasins=("magasin", "nunique"))
    )
    if ref_perf.empty:
        return pd.DataFrame(columns=_COLUMNS)

    # stock reseau disponible (surplus cessible tous magasins) par reference
    dispo = (
        phys.groupby("reference", as_index=False)
        .agg(stock_reseau=("surplus_donneur", "sum"),
             grille=("grille_tailles", lambda s: "/".join(sorted(set(
                 t for lbl in s for t in str(lbl).split("/") if t and t != "-"))[:8])))
    )
    ref_info = ref_perf.merge(dispo, on="reference", how="left")

    # region / type magasin
    region_map: Dict[str, str] = {}
    type_map: Dict[str, str] = {}
    if stores is not None and not stores.empty and "code_magasin" in stores:
        st = stores.drop_duplicates("code_magasin")
        if "region" in st:
            region_map = dict(zip(st["code_magasin"].astype(str), st["region"].astype(str)))
        if "type_magasin" in st:
            type_map = dict(zip(st["code_magasin"].astype(str), st["type_magasin"].astype(str)))

    magasins = phys["magasin"].astype(str).unique()
    perf_max = ref_info["daily_moyen"].max() or 1.0

    rows = []
    for ref_row in ref_info.itertuples(index=False):
        ref = str(ref_row.reference)
        # reference suffisamment repandue et performante pour justifier une extension
        if ref_row.nb_magasins < 2 or ref_row.daily_moyen <= 0:
            continue
        stock_reseau = float(getattr(ref_row, "stock_reseau", 0) or 0)
        if stock_reseau < 2:
            continue
        for mag in magasins:
            if (mag, ref) in present:
                continue
            potentiel = float(ref_row.daily_moyen)
            dispo_score = min(1.0, stock_reseau / 10.0)
            perf_score = min(1.0, potentiel / perf_max)
            score = round(100 * (0.6 * perf_score + 0.4 * dispo_score), 1)
            if score < seuil:
                continue
            rows.append({
                "magasin": mag,
                "reference": ref,
                "region": region_map.get(mag, ""),
                "type_magasin": type_map.get(mag, ""),
                "stock_dispo_reseau": round(stock_reseau, 0),
                "ventes_moyennes_comparables": round(potentiel, 2),
                "nb_magasins_porteurs": int(ref_row.nb_magasins),
                "grille_disponible": getattr(ref_row, "grille", ""),
                "potentiel_estime": round(potentiel * 30, 1),
                "score": score,
                "justification": (f"Vendue dans {int(ref_row.nb_magasins)} magasins "
                                  f"(~{potentiel:.2f}/j), {stock_reseau:.0f} pieces mobilisables reseau"),
            })
    if not rows:
        return pd.DataFrame(columns=_COLUMNS)
    out = pd.DataFrame(rows).sort_values("score", ascending=False).reset_index(drop=True)
    return out


_COLUMNS = [
    "magasin", "reference", "region", "type_magasin", "stock_dispo_reseau",
    "ventes_moyennes_comparables", "nb_magasins_porteurs", "grille_disponible",
    "potentiel_estime", "score", "justification",
]
