"""La marque doit remonter jusqu'aux lignes de transfert (bons de prepa).

Regression : ``generate_from_storage`` ne construisait pas de ``marque_map``,
donc la colonne ``marque`` des transferts restait vide -> pas de marque ni de
regroupement par marque dans les bons de prepa magasin. On verifie desormais
que ``load_real_dataset`` fournit la carte et que ``build_payload`` la porte
sur chaque transfert.
"""

from __future__ import annotations

import io

import pandas as pd

from stockflow.app_service import run_analysis, build_params
from stockflow.ingest_real import load_real_dataset
from stockflow.push_supabase import build_payload

REF = "0200NZ-010"
MARQUE = "NIKE"


def _stock_csv():
    return (
        "Code_Origine,BarCode V2,Taille,Total Stock,Marque Gp\n"
        f"LYON,{REF},M,1,{MARQUE}\nLYON,{REF},L,4,{MARQUE}\nLYON,{REF},S,3,{MARQUE}\n"
        f"PARIS,{REF},M,60,{MARQUE}\nPARIS,{REF},L,60,{MARQUE}\nPARIS,{REF},S,60,{MARQUE}\n"
    )


def _ventes_csv():
    dates = pd.date_range("2026-06-08", "2026-07-12", freq="3D")
    rows = []
    for d in dates:
        ds = d.strftime("%d/%m/%Y")
        for t, q in (("M", 2), ("L", 1), ("S", 1)):
            rows.append(("LYON", REF, t, q, 35.0 * q, ds, MARQUE, "26 Q2", 35.0))
        rows.append(("PARIS", REF, "M", 1, 35.0, ds, MARQUE, "26 Q2", 35.0))
    v = pd.DataFrame(rows, columns=[
        "Code_Origine", "BarCode V2", "Taille", "Total QteVenteRetail",
        "Total MtVenteRetailTTC", "Jours dans Date", "Marque Gp", "Saison", "PrixVente"])
    return v.to_csv(index=False)


def _bytes(s):
    return io.BytesIO(s.encode("utf-8"))


def test_load_real_dataset_expose_marque_map():
    ds = load_real_dataset(_bytes(_stock_csv()), _bytes(_ventes_csv()),
                           objectif_csv=None, today=pd.Timestamp("2026-07-13"))
    mm = ds.get("marque_map")
    assert mm, "marque_map absente"
    assert mm.get((REF, "")) == MARQUE


def test_marque_portee_sur_les_transferts():
    today = pd.Timestamp("2026-07-13")
    result, ds = run_analysis(
        stock=_bytes(_stock_csv()), ventes=_bytes(_ventes_csv()),
        central_stock=None, params=build_params(cible=14, seuil_score=50), today=today)
    assert result.transfers is not None and not result.transfers.empty
    meta = {"runid": "t", "marque_map": ds.get("marque_map", {}),
            "designation_map": ds.get("designation_map", {})}
    _, transfers = build_payload(result, meta)
    assert transfers
    assert all(t["marque"] == MARQUE for t in transfers)
