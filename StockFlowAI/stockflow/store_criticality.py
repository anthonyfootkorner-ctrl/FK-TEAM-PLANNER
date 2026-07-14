"""Modules 7 & 8 - Top 30 par magasin et indice de criticite.

Module 7 : pour chaque magasin, les N meilleures references (CA, quantite,
vitesse), avec couverture, risque de rupture a 7/14 jours et besoin residuel.

Module 8 : un indice de criticite par magasin, recalcule a chaque execution,
combinant risque de rupture sur le Top N, potentiel commercial, statut flagship,
couverture moyenne et tendance. Les ponderations sont parametrables.
"""

from __future__ import annotations

from typing import Dict, Set

import numpy as np
import pandas as pd

from .parameters import Parameters


def compute_top_references(df: pd.DataFrame, params: Parameters) -> pd.DataFrame:
    """Top N references par magasin (agrege toutes tailles/couleurs)."""
    top_n = int(params.get("top_n_references", 30))
    agg = (
        df.groupby(["magasin", "reference"], as_index=False, dropna=False)
        .agg(
            ca_35j=("ca_35j", "sum"),
            ventes_35j=("ventes_35j", "sum"),
            ventes_7j=("ventes_7j", "sum"),
            stock_projete=("stock_projete", "sum"),
            moyenne_quotidienne=("moyenne_quotidienne", "sum"),
            grille_qualite=("grille_qualite", "mean"),
            besoin_residuel=("besoin_residuel", "sum"),
        )
    )
    # couverture agregee
    dormant = float(params.get("couverture_dormant", 999))
    daily = agg["moyenne_quotidienne"]
    agg["couverture"] = np.where(
        daily > 0,
        agg["stock_projete"] / daily.replace(0, np.nan),
        np.where(agg["stock_projete"] > 0, dormant, 0.0),
    )
    agg["jours_avant_rupture"] = agg["couverture"].round(1)
    agg["risque_7j"] = agg["couverture"] < 7
    agg["risque_14j"] = agg["couverture"] < 14

    # classement par magasin : score de vente composite (CA + quantite + vitesse)
    agg["score_vente"] = (
        agg["ca_35j"].rank(pct=True)
        + agg["ventes_35j"].rank(pct=True)
        + agg["ventes_7j"].rank(pct=True)
    )
    agg["rang"] = agg.groupby("magasin")["score_vente"].rank(ascending=False, method="first")
    top = agg[agg["rang"] <= top_n].copy()
    top["dans_top"] = True
    return top.sort_values(["magasin", "rang"]).reset_index(drop=True)


def _normalize(series: pd.Series) -> pd.Series:
    lo, hi = series.min(), series.max()
    if hi - lo < 1e-9:
        return pd.Series(0.5, index=series.index)
    return (series - lo) / (hi - lo)


def compute_store_criticality(df: pd.DataFrame, top: pd.DataFrame,
                              stores: pd.DataFrame, params: Parameters,
                              web_codes: Set[str]) -> pd.DataFrame:
    """Indice de criticite (0-100) par magasin."""
    weights = params.get("poids_criticite", {})
    is_web = df["magasin"].astype(str).str.upper().isin(web_codes)
    phys = df[~is_web]

    # agregats magasin
    grp = phys.groupby("magasin", as_index=False, dropna=False).agg(
        couverture_moyenne=("couverture_projetee", "mean"),
        potentiel=("ca_35j", "sum"),
        ventes_7j=("ventes_7j", "sum"),
        ventes_35j=("ventes_35j", "sum"),
        grille_moyenne=("grille_qualite", "mean"),
    )

    # risque sur le top N
    top_risk = (
        top.groupby("magasin", as_index=False)
        .agg(nb_top=("reference", "count"),
             nb_risque_7j=("risque_7j", "sum"),
             nb_risque_14j=("risque_14j", "sum"))
    )
    grp = grp.merge(top_risk, on="magasin", how="left")
    grp[["nb_top", "nb_risque_7j", "nb_risque_14j"]] = grp[["nb_top", "nb_risque_7j", "nb_risque_14j"]].fillna(0)
    grp["part_risque_top"] = np.where(grp["nb_top"] > 0, grp["nb_risque_14j"] / grp["nb_top"], 0.0)

    # flagship
    flag_map: Dict[str, bool] = {}
    prio_map: Dict[str, float] = {}
    if stores is not None and not stores.empty and "code_magasin" in stores:
        st = stores.drop_duplicates("code_magasin")
        flag_map = dict(zip(st["code_magasin"].astype(str), st.get("flagship", False)))
        if "priorite" in st:
            prio_map = dict(zip(st["code_magasin"].astype(str), st["priorite"]))
    grp["flagship"] = grp["magasin"].astype(str).map(flag_map).fillna(False)
    grp["priorite"] = grp["magasin"].astype(str).map(prio_map).fillna(0.0)

    # tendance magasin : rythme 7j vs 35j
    with np.errstate(divide="ignore", invalid="ignore"):
        rythme7 = grp["ventes_7j"] / 7.0
        rythme35 = grp["ventes_35j"] / 35.0
        grp["tendance"] = np.where(rythme35 > 0, (rythme7 - rythme35) / rythme35, 0.0)

    # composantes normalisees (0-1)
    c_risque = grp["part_risque_top"]
    c_potentiel = _normalize(grp["potentiel"])
    c_flagship = grp["flagship"].astype(float)
    c_couv = 1.0 - _normalize(grp["couverture_moyenne"].clip(upper=60))  # faible couverture = critique
    c_tendance = _normalize(grp["tendance"].clip(-1, 2))

    score = (
        weights.get("risque_rupture_top30", 0.40) * c_risque
        + weights.get("potentiel_commercial", 0.25) * c_potentiel
        + weights.get("flagship", 0.15) * c_flagship
        + weights.get("couverture_moyenne", 0.10) * c_couv
        + weights.get("tendance", 0.10) * c_tendance
    )
    grp["indice_criticite"] = (score * 100).round(1)
    grp = grp.sort_values("indice_criticite", ascending=False).reset_index(drop=True)
    return grp
