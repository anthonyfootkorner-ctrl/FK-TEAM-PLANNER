"""Anti-doublon : une taille deja reapprovisionnee par le CENTRAL ne doit pas
redeclencher un transfert inter-magasins « ameliore la grille ».

Bug constate (RECORDTEE-100) : le reassort central envoyait deja une taille a un
magasin (stock en transit), mais la grille etait calculee sur le stock ACTUEL —
la taille apparaissait « manquante » et un transfert grille inter-magasins etait
propose en plus, sur-approvisionnant le magasin.

Scenario : LYON n'a que le S d'une reference (grille incomplete) mais la vend.
Le CENTRAL a du M/L -> il les envoie a LYON. On verifie qu'aucun transfert
inter-magasins M/L n'est propose vers LYON quand le central les couvre, alors
que SANS central, LYON les recevrait bien d'un autre magasin.
"""

from __future__ import annotations

import io

import pandas as pd

from stockflow.app_service import run_analysis, build_params

REF = "0200NZ-010"


def _stock_csv():
    # LYON n'a que le S (grille incomplete : M et L absents). PARIS a du surplus.
    return (
        "Code_Origine,BarCode V2,Taille,Total Stock,Marque Gp\n"
        f"LYON,{REF},S,3,NIKE\n"
        f"PARIS,{REF},S,60,NIKE\nPARIS,{REF},M,60,NIKE\nPARIS,{REF},L,60,NIKE\n"
    )


def _ventes_csv():
    dates = pd.date_range("2026-06-08", "2026-07-12", freq="3D")
    rows = []
    for d in dates:
        ds = d.strftime("%d/%m/%Y")
        for t in ("S", "M", "L"):               # LYON vend S, M et L
            rows.append(("LYON", REF, t, 2, 70.0, ds, "NIKE", "26 Q2", 35.0))
        rows.append(("PARIS", REF, "S", 1, 35.0, ds, "NIKE", "26 Q2", 35.0))
    v = pd.DataFrame(rows, columns=[
        "Code_Origine", "BarCode V2", "Taille", "Total QteVenteRetail",
        "Total MtVenteRetailTTC", "Jours dans Date", "Marque Gp", "Saison", "PrixVente"])
    return v.to_csv(index=False)


def _central_tsv():
    return (
        "Référence\tCouleur\tTaille\tStock\tMagasin\n"
        f"{REF}\tNOIR\tM\t80\tCENTRAL\n{REF}\tNOIR\tL\t80\tCENTRAL\n{REF}\tNOIR\tS\t80\tCENTRAL\n"
    ).encode("latin1")


def _b(s):
    return io.BytesIO(s.encode())


def _lyon_recoit(res, tailles):
    t = res.transfers
    if t is None or t.empty:
        return {}
    sub = t[(t["reference"] == REF) & (t["destinataire"] == "LYON") & (t["taille"].isin(tailles))]
    return {row["taille"]: int(row["quantite"]) for _, row in sub.iterrows()}


def test_sans_central_lyon_recoit_les_tailles_manquantes():
    """Controle : sans central, LYON complete sa grille via un transfert magasin."""
    res, _ = run_analysis(stock=_b(_stock_csv()), ventes=_b(_ventes_csv()),
                          central_stock=None,
                          params=build_params(cible=14, seuil_score=50),
                          today=pd.Timestamp("2026-07-13"))
    recu = _lyon_recoit(res, ["M", "L"])
    assert recu, "sans central, LYON devrait recevoir M/L d'un autre magasin"


def test_avec_central_pas_de_doublon_grille():
    """Avec central, les tailles M/L arrivent du central (picking) : aucun
    transfert inter-magasins M/L ne doit doubler l'approvisionnement."""
    res, ds = run_analysis(stock=_b(_stock_csv()), ventes=_b(_ventes_csv()),
                           central_stock=_central_tsv(),
                           params=build_params(cible=14, seuil_score=50),
                           today=pd.Timestamp("2026-07-13"))
    # le central sert bien LYON en M/L (picking)
    pick = ds["picking"]
    pl = pick[(pick["reference"] == REF) & (pick["magasin"] == "LYON")]
    assert set(pl["taille"]) & {"M", "L"}, "le central devrait envoyer M/L a LYON"
    # ... donc aucun transfert inter-magasins M/L vers LYON
    assert _lyon_recoit(res, ["M", "L"]) == {}, "doublon : M/L transferes alors que le central les couvre"
