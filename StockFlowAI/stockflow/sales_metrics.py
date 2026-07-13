"""Module 3 (partie ventes) - Calcul des ventes et tendances.

Rattache les ventes 35j / 7j a la table de travail et calcule :
* la moyenne quotidienne (base 35 jours) ;
* le rythme recent (base 7 jours) ;
* la tendance : hausse / stable / baisse ;
* le nombre de jours depuis la derniere vente.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import schema
from .parameters import Parameters


def attach_sales(base: pd.DataFrame, sales: pd.DataFrame,
                 params: Parameters, today: pd.Timestamp) -> pd.DataFrame:
    """Joint les ventes a la table de travail et calcule les rythmes/tendances."""
    df = base.copy()
    cols = ["ventes_35j", "ventes_7j", "ca_35j", "ca_7j"]
    if sales is not None and not sales.empty:
        s = sales.copy()
        keep = schema.LINE_KEYS + [c for c in cols + ["date_derniere_vente"] if c in s.columns]
        s = s[[c for c in keep if c in s.columns]]
        df = df.merge(s, on=schema.LINE_KEYS, how="left")
    for c in cols:
        if c not in df.columns:
            df[c] = 0.0
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)
    if "date_derniere_vente" not in df.columns:
        df["date_derniere_vente"] = pd.NaT

    periode = float(params.get("periode_ventes", 35))
    periode_tendance = float(params.get("periode_tendance", 7))

    df["moyenne_quotidienne"] = df["ventes_35j"] / periode
    df["rythme_7j"] = df["ventes_7j"] / periode_tendance

    # Tendance : variation relative du rythme recent vs rythme long
    with np.errstate(divide="ignore", invalid="ignore"):
        variation = np.where(
            df["moyenne_quotidienne"] > 0,
            (df["rythme_7j"] - df["moyenne_quotidienne"]) / df["moyenne_quotidienne"],
            np.where(df["rythme_7j"] > 0, 1.0, 0.0),
        )
    df["variation_tendance"] = variation
    seuil_h = float(params.get("seuil_tendance_hausse", 0.15))
    seuil_b = float(params.get("seuil_tendance_baisse", -0.15))
    df["tendance"] = np.select(
        [variation >= seuil_h, variation <= seuil_b],
        ["hausse", "baisse"],
        default="stable",
    )

    # jours depuis derniere vente
    if df["date_derniere_vente"].notna().any():
        delta = (today - df["date_derniere_vente"]).dt.days
        df["jours_depuis_vente"] = delta
    else:
        df["jours_depuis_vente"] = np.nan

    return df
