"""Module simulation - Comparatif avant / apres.

Calcule les indicateurs reseau avant transferts, applique les transferts
retenus, puis recalcule les memes indicateurs. Aucun gain ne doit provenir
d'une erreur de formule : les deux photos utilisent exactement la meme methode.

Point d'attention : un transfert de completion de grille peut creer une ligne
(magasin, ref, couleur, taille) qui n'existait pas dans le stock initial. Les
deux photos sont donc calculees sur l'UNION des lignes initiales et des lignes
creees, ce qui garantit la conservation du stock total (un transfert deplace,
il ne detruit pas).
"""

from __future__ import annotations

from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

from .parameters import Parameters
from .size_grids import GridIndex


LineKey = Tuple[str, str, str, str]


def _coverage(stock: float, daily: float, dormant: float) -> float:
    if daily > 0:
        return stock / daily
    return dormant if stock > 0 else 0.0


def _build_frame(base: pd.DataFrame, stock_map: Dict[LineKey, float]) -> pd.DataFrame:
    """Construit une table (union des lignes base + lignes creees) avec le stock donne."""
    # metadonnees par ligne connue
    daily_map: Dict[LineKey, float] = {}
    web_map: Dict[str, bool] = {}
    ville_map: Dict[str, str] = {}
    cat_map: Dict[Tuple[str, str], str] = {}
    price_by_sku: Dict[Tuple[str, str, str], float] = {}
    for row in base.itertuples(index=False):
        key = (str(row.magasin), str(row.reference), str(row.couleur), str(row.taille))
        daily_map[key] = float(getattr(row, "moyenne_quotidienne", 0) or 0)
        web_map[str(row.magasin)] = bool(getattr(row, "is_web", False))
        ville_map[str(row.magasin)] = getattr(row, "ville", None)
        cat_map[(str(row.reference), str(row.couleur))] = getattr(row, "categorie", None)
        pv = float(getattr(row, "prix_vente", 0) or 0)
        price_by_sku[(str(row.reference), str(row.couleur), str(row.taille))] = pv

    keys = set(daily_map) | set(stock_map)
    rows = []
    for (mag, ref, coul, taille) in keys:
        rows.append({
            "magasin": mag, "reference": ref, "couleur": coul, "taille": taille,
            "stock": stock_map.get((mag, ref, coul, taille), 0.0),
            "moyenne_quotidienne": daily_map.get((mag, ref, coul, taille), 0.0),
            "prix_vente": price_by_sku.get((ref, coul, taille), 0.0),
            "is_web": web_map.get(mag, False),
            "categorie": cat_map.get((ref, coul)),
            "ville": ville_map.get(mag),
        })
    return pd.DataFrame(rows)


def _indicators(frame: pd.DataFrame, grid: GridIndex, params: Parameters) -> Dict:
    dormant = float(params.get("couverture_dormant", 999))
    total_stock = 0.0
    total_value = 0.0
    dormant_units = 0.0
    ruptures = 0
    sous_7j = 0
    sous_14j = 0
    couvertures: List[float] = []
    lignes_actives = 0

    for row in frame.itertuples(index=False):
        stock = float(row.stock)
        total_stock += stock
        total_value += stock * float(row.prix_vente or 0)
        if row.is_web:
            continue  # le web compte dans le stock mais pas dans les KPI service
        daily = float(row.moyenne_quotidienne or 0)
        if daily > 0:
            lignes_actives += 1
            cov = _coverage(stock, daily, dormant)
            couvertures.append(min(cov, dormant))
            if stock <= 0:
                ruptures += 1
            if cov < 7:
                sous_7j += 1
            if cov < 14:
                sous_14j += 1
        elif stock > 0:
            dormant_units += stock

    # grilles physiques (mag+ref+couleur)
    grilles_coherentes = grilles_total = tailles_coeur_dispo = 0
    seen = set()
    for row in frame.itertuples(index=False):
        if row.is_web:
            continue
        key = (str(row.magasin), str(row.reference), str(row.couleur))
        if key in seen:
            continue
        seen.add(key)
        st = grid.state(*key)
        grilles_total += 1
        if st.valide:
            grilles_coherentes += 1
        tailles_coeur_dispo += st.nb_coeur

    couv_moy = float(np.mean(couvertures)) if couvertures else 0.0
    rupture_rate = ruptures / lignes_actives if lignes_actives else 0.0
    grid_rate = grilles_coherentes / grilles_total if grilles_total else 0.0
    core_rate = min(1.0, tailles_coeur_dispo / (grilles_total * 2)) if grilles_total else 0.0
    sante = round(100 * (0.4 * (1 - rupture_rate) + 0.3 * grid_rate + 0.3 * core_rate), 1)

    return {
        "stock_total": round(total_stock, 0),
        "valeur_stock": round(total_value, 0),
        "stock_dormant": round(dormant_units, 0),
        "ruptures": ruptures,
        "refs_sous_7j": sous_7j,
        "refs_sous_14j": sous_14j,
        "couverture_moyenne": round(couv_moy, 1),
        "grilles_coherentes": grilles_coherentes,
        "grilles_total": grilles_total,
        "tailles_coeur_dispo": tailles_coeur_dispo,
        "score_sante_reseau": sante,
    }


def simulate(base: pd.DataFrame, result, params: Parameters, web_codes):
    """Retourne (comparatif_global, comparatif_par_magasin)."""
    dormant = float(params.get("couverture_dormant", 999))

    stock_before: Dict[LineKey, float] = {}
    for row in base.itertuples(index=False):
        key = (str(row.magasin), str(row.reference), str(row.couleur), str(row.taille))
        stock_before[key] = float(getattr(row, "stock_actuel", 0) or 0)
    stock_after = dict(stock_before)
    stock_after.update(result.stock_final)

    frame_before = _build_frame(base, stock_before)
    frame_after = _build_frame(base, stock_after)
    grid_before = GridIndex.from_frame(frame_before, params, stock_col="stock")
    grid_after = GridIndex.from_frame(frame_after, params, stock_col="stock")

    ind_before = _indicators(frame_before, grid_before, params)
    ind_after = _indicators(frame_after, grid_after, params)

    rows = []
    for k in ind_before:
        rows.append({
            "indicateur": k,
            "avant": ind_before[k],
            "apres": ind_after[k],
            "variation": round(ind_after[k] - ind_before[k], 1),
        })

    nb_transferts = 0 if result.transfers is None or result.transfers.empty else len(result.transfers)
    nb_dest = 0
    valeur_deplacee = 0.0
    if nb_transferts:
        nb_dest = int(result.transfers.groupby("expediteur")["destinataire"].nunique().sum())
        prix_map = base.drop_duplicates(["reference", "couleur", "taille"]).set_index(
            ["reference", "couleur", "taille"]).get("prix_vente")
        for t in result.transfers.itertuples(index=False):
            pv = 0.0
            if prix_map is not None:
                try:
                    pv = float(prix_map.loc[(t.reference, t.couleur, t.taille)])
                except Exception:
                    pv = 0.0
            valeur_deplacee += t.quantite * pv
    for label, val in [("nb_transferts", nb_transferts),
                       ("nb_destinations", nb_dest),
                       ("valeur_stock_deplace", round(valeur_deplacee, 0))]:
        rows.append({"indicateur": label, "avant": 0, "apres": val, "variation": val})

    global_df = pd.DataFrame(rows)
    par_mag = _per_store(base, stock_before, stock_after, params, web_codes)
    return global_df, par_mag


def _per_store(base, stock_before, stock_after, params, web_codes) -> pd.DataFrame:
    dormant = float(params.get("couverture_dormant", 999))
    rows: Dict[str, Dict] = {}
    for row in base.itertuples(index=False):
        mag = str(row.magasin)
        if mag.upper() in web_codes:
            continue
        key = (mag, str(row.reference), str(row.couleur), str(row.taille))
        daily = float(getattr(row, "moyenne_quotidienne", 0) or 0)
        r = rows.setdefault(mag, {"magasin": mag, "ruptures_avant": 0, "ruptures_apres": 0,
                                  "cov_sum_avant": 0.0, "cov_sum_apres": 0.0, "n": 0})
        if daily > 0:
            r["n"] += 1
            sb = stock_before.get(key, 0.0)
            sa = stock_after.get(key, 0.0)
            if sb <= 0:
                r["ruptures_avant"] += 1
            if sa <= 0:
                r["ruptures_apres"] += 1
            r["cov_sum_avant"] += min(_coverage(sb, daily, dormant), dormant)
            r["cov_sum_apres"] += min(_coverage(sa, daily, dormant), dormant)
    out = []
    for mag, r in rows.items():
        n = max(1, r["n"])
        out.append({
            "magasin": mag,
            "ruptures_avant": r["ruptures_avant"],
            "ruptures_apres": r["ruptures_apres"],
            "couverture_moyenne_avant": round(r["cov_sum_avant"] / n, 1),
            "couverture_moyenne_apres": round(r["cov_sum_apres"] / n, 1),
        })
    return pd.DataFrame(out).sort_values("magasin").reset_index(drop=True)
