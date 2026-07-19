"""Protection de la grille de tailles cote EXPEDITEUR.

Regle (validee avec le metier) : un magasin physique garde au moins 1 unite de
CHAQUE taille coeur qu'il possede pour une reference — il ne vide jamais une
taille coeur, meme mal vendue. Exception : si la reference est TOTALEMENT morte
chez lui (aucune vente, toutes tailles), la protection saute et on peut la vider
entierement (pas de stock mort piege).

Scenario : PARIS a S=2, M=3, L=1 (S/M/L = tailles coeur). Il ne vend QUE le S.
LYON est en rupture sur M et L et les vend fort -> besoin. Sans protection PARIS
viderait M et L ; avec, il garde 1 M et 1 L.
"""

from __future__ import annotations

import io

import pandas as pd

from stockflow.app_service import run_analysis, build_params

REF = "0200NZ-010"


def _stock_csv():
    return (
        "Code_Origine,BarCode V2,Taille,Total Stock,Marque Gp\n"
        f"PARIS,{REF},S,2,NIKE\nPARIS,{REF},M,3,NIKE\nPARIS,{REF},L,1,NIKE\n"
        f"LYON,{REF},S,5,NIKE\n"
    )


def _ventes_csv(paris_vend_s=True):
    dates = pd.date_range("2026-06-08", "2026-07-12", freq="3D")
    rows = []
    for d in dates:
        ds = d.strftime("%d/%m/%Y")
        if paris_vend_s:                       # PARIS vend le S -> reference vivante
            rows.append(("PARIS", REF, "S", 1, 35.0, ds, "NIKE", "26 Q2", 35.0))
        rows.append(("LYON", REF, "M", 3, 105.0, ds, "NIKE", "26 Q2", 35.0))
        rows.append(("LYON", REF, "L", 2, 70.0, ds, "NIKE", "26 Q2", 35.0))
    v = pd.DataFrame(rows, columns=[
        "Code_Origine", "BarCode V2", "Taille", "Total QteVenteRetail",
        "Total MtVenteRetailTTC", "Jours dans Date", "Marque Gp", "Saison", "PrixVente"])
    return v.to_csv(index=False)


def _b(s):
    return io.BytesIO(s.encode())


def _paris_gives(res):
    t = res.transfers
    out = {}
    if t is not None and not t.empty:
        sub = t[(t["reference"] == REF) & (t["expediteur"] == "PARIS")]
        for _, r in sub.iterrows():
            out[r["taille"]] = out.get(r["taille"], 0) + int(r["quantite"])
    return out


def _run(protection, paris_vend_s=True):
    p = build_params(cible=21, seuil_score=40)
    p.set("protection_grille_expediteur", protection)
    res, _ = run_analysis(stock=_b(_stock_csv()), ventes=_b(_ventes_csv(paris_vend_s)),
                          central_stock=None, params=p, today=pd.Timestamp("2026-07-13"))
    return res


def test_protection_garde_une_de_chaque_taille_coeur():
    give = _paris_gives(_run(protection=True))
    # M : 3 en stock, garde 1 -> donne au plus 2
    assert give.get("M", 0) <= 2
    # L : 1 en stock (taille coeur) -> il la garde, ne donne rien
    assert give.get("L", 0) == 0


def test_sans_protection_il_vide_les_tailles_coeur():
    give = _paris_gives(_run(protection=False))
    assert give.get("M", 0) == 3      # vide le M
    assert give.get("L", 0) == 1      # vide le L (derniere piece)


def test_reference_morte_liquidation_totale_malgre_protection():
    # PARIS ne vend RIEN (aucune vente, toutes tailles) -> reference morte chez lui
    give = _paris_gives(_run(protection=True, paris_vend_s=False))
    assert give.get("M", 0) == 3
    assert give.get("L", 0) == 1
