"""Module 2 - Calcul des stocks projetes.

Stock projete = stock actuel
              + reassorts Picking en transit (non receptionnes)
              + receptions validees
              - sorties deja programmees

Le moteur raisonne toujours sur le stock projete, jamais sur le seul stock
physique. On construit ici la table de travail au niveau
(magasin, reference, couleur, taille) qui sert de socle a tous les modules.
"""

from __future__ import annotations

from typing import Iterable, Set

import numpy as np
import pandas as pd

from . import schema
from .parameters import Parameters


# statuts picking consideres comme *deja receptionnes* (donc plus en transit)
STATUTS_RECEPTIONNES = {"receptionne", "recu", "recue", "livre", "livree", "closed", "termine", "clos"}


def web_store_codes(stores: pd.DataFrame, stocks: pd.DataFrame,
                    params: Parameters) -> Set[str]:
    """Determine l'ensemble des codes magasins consideres comme 'Web'.

    Un magasin est Web si :
    * son code figure dans le parametre ``magasins_web`` ; ou
    * son type_magasin vaut WEB ; ou
    * son code contient 'WEB'.
    """
    codes: Set[str] = set()
    for c in params.get("magasins_web", []) or []:
        codes.add(str(c).strip().upper())
    if stores is not None and not stores.empty and "code_magasin" in stores:
        st = stores
        if "type_magasin" in st:
            mask = st["type_magasin"].astype(str).str.upper().str.contains("WEB", na=False)
            codes.update(st.loc[mask, "code_magasin"].astype(str).str.upper())
        codes.update(
            st.loc[st["code_magasin"].astype(str).str.upper().str.contains("WEB", na=False),
                   "code_magasin"].astype(str).str.upper()
        )
    if stocks is not None and not stocks.empty and "magasin" in stocks:
        mask = stocks["magasin"].astype(str).str.upper().str.contains("WEB", na=False)
        codes.update(stocks.loc[mask, "magasin"].astype(str).str.upper())
    return codes


def picking_in_transit(picking: pd.DataFrame) -> pd.DataFrame:
    """Agrege les quantites Picking *non receptionnees* par ligne receveur.

    Seuls les reassorts non receptionnes comptent comme stock en transit
    (brief 3.3). Ils ne devront jamais etre doubles par le moteur.
    """
    if picking is None or picking.empty:
        return pd.DataFrame(columns=schema.LINE_KEYS + ["stock_transit"])
    df = picking.copy()
    statut = df.get("statut_reassort", pd.Series([""] * len(df))).astype(str).str.strip().str.lower()
    en_transit = ~statut.isin(STATUTS_RECEPTIONNES)
    df = df[en_transit]
    if df.empty:
        return pd.DataFrame(columns=schema.LINE_KEYS + ["stock_transit"])
    grp = (
        df.groupby(schema.LINE_KEYS, as_index=False, dropna=False)["quantite_prevue"]
        .sum()
        .rename(columns={"quantite_prevue": "stock_transit"})
    )
    return grp


def build_base(stocks: pd.DataFrame, picking: pd.DataFrame, stores: pd.DataFrame,
               params: Parameters) -> pd.DataFrame:
    """Construit la table de travail avec stock actuel / transit / projete."""
    base = stocks.copy()

    # stock actuel = stock disponible si present sinon physique
    if "stock_disponible" in base:
        base["stock_actuel"] = base["stock_disponible"]
    else:
        base["stock_actuel"] = base["stock_physique"]

    # Picking en transit
    transit = picking_in_transit(picking)
    base = base.merge(transit, on=schema.LINE_KEYS, how="left")
    base["stock_transit"] = base["stock_transit"].fillna(0.0)

    # receptions validees / sorties programmees : colonnes optionnelles
    base["reception_validee"] = base.get("reception_validee", 0.0)
    base["sorties_programmees"] = base.get("sorties_programmees", 0.0)
    base["reception_validee"] = pd.to_numeric(base["reception_validee"], errors="coerce").fillna(0.0)
    base["sorties_programmees"] = pd.to_numeric(base["sorties_programmees"], errors="coerce").fillna(0.0)

    base["stock_projete"] = (
        base["stock_actuel"]
        + base["stock_transit"]
        + base["reception_validee"]
        - base["sorties_programmees"]
    ).clip(lower=0)

    # marquage Web
    web_codes = web_store_codes(stores, stocks, params)
    base["is_web"] = base["magasin"].astype(str).str.upper().isin(web_codes)

    # rattachement ville depuis le fichier magasins si absente du stock
    if stores is not None and not stores.empty and "code_magasin" in stores and "ville" in stores:
        ville_map = (
            stores.dropna(subset=["code_magasin"])
            .drop_duplicates("code_magasin")
            .set_index(stores.dropna(subset=["code_magasin"]).drop_duplicates("code_magasin")["code_magasin"].astype(str))["ville"]
            .to_dict()
        )
        if "ville" not in base or base["ville"].isna().all():
            base["ville"] = base["magasin"].astype(str).map(ville_map)
        else:
            base["ville"] = base["ville"].where(
                base["ville"].astype(str).str.strip().replace({"nan": ""}) != "",
                base["magasin"].astype(str).map(ville_map),
            )

    return base
