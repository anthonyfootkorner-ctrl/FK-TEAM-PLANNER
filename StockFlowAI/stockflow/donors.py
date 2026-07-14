"""Module 5 - Detection des donneurs.

Un magasin (ligne magasin+ref+couleur+taille) est donneur potentiel si :
* sa couverture est superieure au besoin (surplus mobilisable) ;
* il conserve au moins la couverture minimale expediteur apres don ;
* la reference n'est pas exclue / protegee ;
* aucun mouvement recent ne rend le transfert inutile (delai de protection).

Le Web est un donneur specifique : il peut ceder meme des tailles isolees mais
doit rester au-dessus de sa couverture minimale de protection.
"""

from __future__ import annotations

from typing import Set

import numpy as np
import pandas as pd

from .parameters import Parameters


def _excluded_mask(df: pd.DataFrame, params: Parameters) -> pd.Series:
    mask = pd.Series(False, index=df.index)
    excl_ref = {str(x).strip().upper() for x in params.get("exclusions_reference", []) or []}
    excl_marque = {str(x).strip().upper() for x in params.get("exclusions_marque", []) or []}
    excl_saison = {str(x).strip().upper() for x in params.get("exclusions_saison", []) or []}
    if excl_ref and "reference" in df:
        mask |= df["reference"].astype(str).str.upper().isin(excl_ref)
    if excl_marque and "marque" in df:
        mask |= df["marque"].astype(str).str.upper().isin(excl_marque)
    if excl_saison and "saison" in df:
        mask |= df["saison"].astype(str).str.upper().isin(excl_saison)
    return mask


def _recently_moved(df: pd.DataFrame, history: pd.DataFrame,
                    params: Parameters, today: pd.Timestamp) -> pd.Series:
    """Ligne recemment recue (delai de protection) => ne pas re-transferer."""
    protege = pd.Series(False, index=df.index)
    if history is None or history.empty or "date_reception" not in history.columns:
        return protege
    delai = int(params.get("delai_protection_jours", 21))
    recent = history[history["date_reception"].notna()].copy()
    if recent.empty:
        return protege
    recent = recent[(today - recent["date_reception"]).dt.days <= delai]
    if recent.empty:
        return protege
    recus = set(
        zip(recent["destinataire"].astype(str), recent["reference"].astype(str),
            recent["couleur"].astype(str), recent["taille"].astype(str))
    )
    keys = list(zip(df["magasin"].astype(str), df["reference"].astype(str),
                    df["couleur"].astype(str), df["taille"].astype(str)))
    return pd.Series([k in recus for k in keys], index=df.index)


def detect_donors(df: pd.DataFrame, params: Parameters, web_codes: Set[str],
                  history: pd.DataFrame, today: pd.Timestamp) -> pd.DataFrame:
    """Renvoie les lignes donneuses avec la quantite cessible ``qte_don_max``."""
    df = df.copy()

    exclu = _excluded_mask(df, params)
    # magasins hors flux : reserve externe (CENTRAL) ou magasin ferme/inactif
    exclus_flux = params.excluded_stores()
    if exclus_flux:
        exclu = exclu | df["magasin"].astype(str).str.upper().isin(exclus_flux)
    protege = _recently_moved(df, history, params, today)

    is_web = df["is_web"] if "is_web" in df else df["magasin"].astype(str).str.upper().isin(web_codes)

    # magasins physiques : surplus au-dela de la couverture min expediteur
    qte_don = df["surplus_donneur"].copy()

    # Web : protege par sa couverture minimale propre
    cov_min_web = float(params.get("couverture_min_web", 30))
    daily = df["moyenne_quotidienne"]
    seuil_web = np.ceil(cov_min_web * daily)
    # si le web ne vend pas la ligne (daily=0) il peut tout ceder au dela de 0
    qte_web = np.maximum(0.0, df["stock_actuel"] - seuil_web)
    qte_don = np.where(is_web, qte_web, qte_don)

    df["qte_don_max"] = np.floor(np.maximum(0.0, qte_don)).astype(float)
    df["donneur_exclu"] = exclu
    df["donneur_protege"] = protege

    eligible = (df["qte_don_max"] >= 1) & (~exclu) & (~protege)
    df["est_donneur"] = eligible

    donors = df[eligible].copy()
    donors["motif_donneur"] = np.where(
        donors["is_web"], "Reserve Web au-dessus du seuil",
        np.where(donors["stock_dormant"], "Stock dormant / faibles ventes",
                 "Surplus de couverture (>20j conserves)"),
    )
    return donors
