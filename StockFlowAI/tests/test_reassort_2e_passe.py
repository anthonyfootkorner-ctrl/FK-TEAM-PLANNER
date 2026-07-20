"""2e passe du reassort central : completer une grille APRES l'inter-magasins.

Le central retient une taille dont il ne peut pas faire une grille valide a lui
seul (« courbe rompue »). Mais si l'inter-magasins apporte ensuite les autres
tailles, cette taille completerait desormais la grille : la 2e passe la relache.

Scenario (mime le cas reel KA8193) : le CENTRAL n'a la reference qu'en XS. LYON
n'a que le S et vend XS/S/L. En 1re passe le central retient le XS (S+XS = 2
tailles coeur < 3). L'inter-magasins envoie le L (depuis PARIS). Apres coup,
LYON a S + L : le XS du central complete la grille -> la 2e passe l'envoie.
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
        f"PARIS,{REF},S,60,NIKE\nPARIS,{REF},L,60,NIKE\n"
    )


def _ventes_csv():
    dates = pd.date_range("2026-06-08", "2026-07-12", freq="3D")
    rows = []
    for d in dates:
        ds = d.strftime("%d/%m/%Y")
        for t in ("XS", "S", "L"):              # LYON vend XS, S et L
            rows.append(("LYON", REF, t, 2, 70.0, ds, "NIKE", "26 Q2", 35.0))
        rows.append(("PARIS", REF, "S", 1, 35.0, ds, "NIKE", "26 Q2", 35.0))
    v = pd.DataFrame(rows, columns=[
        "Code_Origine", "BarCode V2", "Taille", "Total QteVenteRetail",
        "Total MtVenteRetailTTC", "Jours dans Date", "Marque Gp", "Saison", "PrixVente"])
    return v.to_csv(index=False)


def _central_tsv():
    # le central n'a QUE du XS pour cette reference
    return (f"Référence\tCouleur\tTaille\tStock\tMagasin\n{REF}\tNOIR\tXS\t50\tCENTRAL\n").encode("latin1")


def _b(s):
    return io.BytesIO(s.encode())


def _lyon_xs(datasets):
    rc = datasets["reassort_central"]
    if rc is None or rc.empty:
        return 0
    sub = rc[(rc["barcode"].astype(str) == REF) & (rc["boutique"] == "LYON")
             & (rc["taille"].astype(str).str.upper() == "XS")]
    return int(sub["qte_proposee"].sum()) if not sub.empty else 0


def _run(deuxieme_passe):
    p = build_params(cible=14, seuil_score=50)
    p.set("reassort_central_2e_passe", deuxieme_passe)
    # ce test cible la 2e passe : on desactive la regle grille receveur qui,
    # sinon, annulerait le transfert isole du L vers LYON (S+L = 2 tailles coeur).
    p.set("min_grille_receveur_intershop", 0)
    res, ds = run_analysis(stock=_b(_stock_csv()), ventes=_b(_ventes_csv()),
                           central_stock=_central_tsv(), params=p,
                           today=pd.Timestamp("2026-07-13"))
    return res, ds


def test_sans_2e_passe_le_xs_reste_retenu():
    _, ds = _run(deuxieme_passe=False)
    assert _lyon_xs(ds) == 0, "sans 2e passe, le central ne doit pas envoyer le XS (grille rompue)"


def test_avec_2e_passe_le_xs_est_relache():
    res, ds = _run(deuxieme_passe=True)
    # l'inter-magasins a bien apporte le L a LYON (prealable de la 2e passe)
    t = res.transfers
    got_l = (not t.empty) and not t[(t["reference"] == REF) & (t["destinataire"] == "LYON")
                                    & (t["taille"] == "L")].empty
    assert got_l, "pre-requis : LYON doit recevoir le L en inter-magasins"
    # ... donc la 2e passe relache le XS du central pour completer la grille
    assert _lyon_xs(ds) > 0, "avec 2e passe, le central doit envoyer le XS retenu"
