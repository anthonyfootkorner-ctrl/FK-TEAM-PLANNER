"""Anti-taille isolée côté receveur (inter-magasins).

Un magasin ne reçoit une référence que si, au final (rayon + reçu), il atteint
``min_grille_receveur_intershop`` tailles cœur. Sinon on n'envoie RIEN sur cette
référence (pas de taille isolée).

Scénario : LYON n'a que le S d'une référence (S/M/L = tailles cœur) et vend le M
(rupture). PARIS a du surplus de M. LYON ne pourrait obtenir que le M -> S+M =
2 tailles cœur seulement. Avec la règle à 3, ce transfert isolé est annulé ;
désactivée (0), il passe.
"""

from __future__ import annotations

import io

import pandas as pd

from stockflow.app_service import run_analysis, build_params

REF = "0200NZ-010"


def _stock_csv():
    return (
        "Code_Origine,BarCode V2,Taille,Total Stock,Marque Gp\n"
        f"LYON,{REF},S,3,NIKE\n"
        f"PARIS,{REF},S,60,NIKE\nPARIS,{REF},M,60,NIKE\n"
    )


def _ventes_csv():
    dates = pd.date_range("2026-06-08", "2026-07-12", freq="3D")
    rows = []
    for d in dates:
        ds = d.strftime("%d/%m/%Y")
        for t in ("S", "M"):                    # LYON vend S et M (pas le L)
            rows.append(("LYON", REF, t, 2, 70.0, ds, "NIKE", "26 Q2", 35.0))
        rows.append(("PARIS", REF, "S", 1, 35.0, ds, "NIKE", "26 Q2", 35.0))
    v = pd.DataFrame(rows, columns=[
        "Code_Origine", "BarCode V2", "Taille", "Total QteVenteRetail",
        "Total MtVenteRetailTTC", "Jours dans Date", "Marque Gp", "Saison", "PrixVente"])
    return v.to_csv(index=False)


def _b(s):
    return io.BytesIO(s.encode())


def _lyon_recoit(res):
    t = res.transfers
    if t is None or t.empty:
        return 0
    return int(t[(t["reference"] == REF) & (t["destinataire"] == "LYON")]["quantite"].sum())


def _run(min_grille):
    p = build_params(cible=14, seuil_score=50)
    p.set("min_grille_receveur_intershop", min_grille)
    res, _ = run_analysis(stock=_b(_stock_csv()), ventes=_b(_ventes_csv()),
                          central_stock=None, params=p, today=pd.Timestamp("2026-07-13"))
    return res


def test_regle_off_le_transfert_isole_passe():
    assert _lyon_recoit(_run(min_grille=0)) > 0


def test_regle_3_annule_le_transfert_isole():
    # LYON n'atteindrait que S+M = 2 tailles coeur -> rien ne doit lui etre envoye
    assert _lyon_recoit(_run(min_grille=3)) == 0
