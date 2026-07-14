"""Module 3 (partie couverture) - Couvertures et besoin residuel.

Couverture en jours = stock projete / ventes moyennes quotidiennes.

Cas particuliers (brief module 3) :
* stock = 0        -> couverture = 0 ;
* stock > 0 sans vente -> couverture = 999 (statut dormant).

Le besoin residuel integre deja le Picking en transit (present dans le stock
projete), ce qui evite les doubles reassorts (regle anti-double, module 5.1).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .parameters import Parameters


def _couverture(stock: pd.Series, daily: pd.Series, dormant_value: float) -> pd.Series:
    cov = np.where(
        daily > 0,
        stock / daily.replace(0, np.nan),
        np.where(stock > 0, dormant_value, 0.0),
    )
    return pd.Series(cov, index=stock.index).astype(float)


def compute_coverage(df: pd.DataFrame, params: Parameters) -> pd.DataFrame:
    df = df.copy()
    dormant_value = float(params.get("couverture_dormant", 999))
    daily = df["moyenne_quotidienne"]

    df["couverture_actuelle"] = _couverture(df["stock_actuel"], daily, dormant_value)
    df["couverture_projetee"] = _couverture(df["stock_projete"], daily, dormant_value)

    # Besoin : quantite pour atteindre la couverture cible receveur
    cible = float(params.get("couverture_cible_magasin", 30))
    besoin_cible = np.ceil(cible * daily)
    df["besoin_cible"] = besoin_cible

    # Besoin residuel = ce qu'il reste a couvrir apres stock projete (donc apres Picking)
    df["besoin_residuel"] = np.maximum(0.0, besoin_cible - df["stock_projete"])
    # arrondi entier (pieces)
    df["besoin_residuel"] = np.ceil(df["besoin_residuel"]).astype(float)

    # Stock dormant : du stock, aucune vente recente
    seuil_dormant = float(params.get("seuil_dormant_jours", 60))
    sans_vente = df["moyenne_quotidienne"] <= 0
    vieux = df.get("jours_depuis_vente")
    if vieux is not None:
        vieux_mask = vieux.fillna(9999) >= seuil_dormant
    else:
        vieux_mask = pd.Series(False, index=df.index)
    df["stock_dormant"] = ((sans_vente | vieux_mask) & (df["stock_actuel"] > 0))
    df["qte_dormante"] = np.where(df["stock_dormant"], df["stock_actuel"], 0.0)

    # Surplus mobilisable cote donneur : stock au dela de la couverture minimale
    cov_min_exp = float(params.get("couverture_min_expediteur", 20))
    seuil_conservation = np.where(daily > 0, np.ceil(cov_min_exp * daily), 0.0)
    df["seuil_conservation"] = seuil_conservation
    df["surplus_donneur"] = np.maximum(0.0, df["stock_actuel"] - seuil_conservation)

    return df
