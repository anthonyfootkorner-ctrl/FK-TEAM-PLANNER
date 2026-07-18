"""Tests du reassort central (CENTRAL -> boutiques) et du chainage picking.

Verifie que :
* le reassort central propose bien un approvisionnement depuis CENTRAL pour une
  boutique en rupture, dans la limite du stock CENTRAL et de la couverture cible ;
* la conversion en picking produit les colonnes attendues (reference = code-barre
  complet, taille normalisee, quantite positive) ;
* le chainage « A + B » nette le besoin : quand le reassort central couvre la
  rupture, le moteur inter-magasins ne double PAS le transfert.
"""

from __future__ import annotations

import io

import pandas as pd
import pytest

from stockflow.app_service import run_analysis, build_params
from stockflow.reassort_central import (
    compute_reassort_central,
    proposed_to_picking,
    build_fastmag_import,
)

REF = "0200NZ-010"


def _stock_csv(lyon_m=1, paris_m=60):
    return (
        "Code_Origine,BarCode V2,Taille,Total Stock,Marque Gp\n"
        f"LYON,{REF},M,{lyon_m},NIKE\n"
        f"LYON,{REF},L,4,NIKE\n"
        f"LYON,{REF},S,3,NIKE\n"
        f"PARIS,{REF},M,{paris_m},NIKE\n"
        f"PARIS,{REF},L,60,NIKE\n"
        f"PARIS,{REF},S,60,NIKE\n"
    )


def _ventes_csv():
    dates = pd.date_range("2026-06-08", "2026-07-12", freq="3D")
    rows = []
    for d in dates:
        ds = d.strftime("%d/%m/%Y")
        for t, q in (("M", 2), ("L", 1), ("S", 1)):
            rows.append(("LYON", REF, t, q, 35.0 * q, ds, "NIKE", "26 Q2", 35.0))
        rows.append(("PARIS", REF, "M", 1, 35.0, ds, "NIKE", "26 Q2", 35.0))
    v = pd.DataFrame(rows, columns=[
        "Code_Origine", "BarCode V2", "Taille", "Total QteVenteRetail",
        "Total MtVenteRetailTTC", "Jours dans Date", "Marque Gp", "Saison", "PrixVente"])
    return v.to_csv(index=False)


def _central_tsv(m=100, l=50, s=50):
    return (
        "Référence\tCouleur\tTaille\tStock\tMagasin\n"
        f"{REF}\tNOIR\tM\t{m}\tCENTRAL\n"
        f"{REF}\tNOIR\tL\t{l}\tCENTRAL\n"
        f"{REF}\tNOIR\tS\t{s}\tCENTRAL\n"
    )


def _bytes(s, enc="utf-8"):
    return io.BytesIO(s.encode(enc))


def test_reassort_central_propose_depuis_central():
    res = compute_reassort_central(
        stock=_bytes(_stock_csv()), ventes=_bytes(_ventes_csv()),
        central_stock=_central_tsv().encode("latin1"),
    )
    assert res.ok
    assert res.central_total == 200
    p = res.proposed
    # LYON en rupture sur M (stock 1, ~0.7 vente/j) : doit etre approvisionne
    m = p[(p["boutique"] == "LYON") & (p["taille"] == "M")]
    assert not m.empty
    qte = int(m["qte_proposee"].iloc[0])
    assert qte > 0
    # borne : ne depasse pas le stock CENTRAL disponible
    assert qte <= 100
    # priorite rupture/urgence
    assert m["priorite"].iloc[0].startswith("P1")


def test_proposed_to_picking_colonnes():
    res = compute_reassort_central(
        stock=_bytes(_stock_csv()), ventes=_bytes(_ventes_csv()),
        central_stock=_central_tsv().encode("latin1"),
    )
    pick = proposed_to_picking(res.proposed)
    assert not pick.empty
    assert set(["magasin", "reference", "couleur", "taille",
                "quantite_prevue", "statut_reassort", "id_mouvement"]).issubset(pick.columns)
    # reference = code-barre complet (= reference StockFlow)
    assert (pick["reference"] == REF).all()
    assert (pick["quantite_prevue"] > 0).all()
    assert (pick["statut_reassort"] == "PROPOSE").all()


def test_chainage_nette_le_besoin():
    """Avec reassort central, la rupture LYON est couverte par CENTRAL ; le
    moteur inter-magasins ne doit donc PAS reproposer PARIS -> LYON pour M."""
    today = pd.Timestamp("2026-07-13")

    res_sans, ds_sans = run_analysis(
        stock=_bytes(_stock_csv()), ventes=_bytes(_ventes_csv()),
        central_stock=None, params=build_params(cible=14, seuil_score=50), today=today)
    t_sans = res_sans.transfers
    inter_m_sans = t_sans[(t_sans["reference"] == REF) & (t_sans["taille"] == "M")] \
        if t_sans is not None and not t_sans.empty else pd.DataFrame()
    assert not inter_m_sans.empty  # sans central : transfert inter-magasin attendu

    res_avec, ds_avec = run_analysis(
        stock=_bytes(_stock_csv()), ventes=_bytes(_ventes_csv()),
        central_stock=_central_tsv().encode("latin1"),
        params=build_params(cible=14, seuil_score=50), today=today)
    # le picking (reassort central) est bien injecte
    assert not ds_avec["picking"].empty
    assert "reassort_central" in ds_avec and not ds_avec["reassort_central"].empty
    t_avec = res_avec.transfers
    inter_m_avec = t_avec[(t_avec["reference"] == REF) & (t_avec["taille"] == "M")] \
        if t_avec is not None and not t_avec.empty else pd.DataFrame()
    qte_avec = int(inter_m_avec["quantite"].sum()) if not inter_m_avec.empty else 0
    qte_sans = int(inter_m_sans["quantite"].sum())
    # le reassort central couvre la rupture => besoin residuel inter-magasin nul (ou reduit)
    assert qte_avec < qte_sans


def test_reserve_absente_message_clair():
    res = compute_reassort_central(
        stock=_bytes(_stock_csv()), ventes=_bytes(_ventes_csv()),
        central_stock=None,   # pas de central, et pas de CENTRAL dans le stock
    )
    assert not res.ok
    assert "CENTRAL" in res.message


def test_fastmag_import_vide_sans_proposition(tmp_path):
    nb, nbb, sans = build_fastmag_import(pd.DataFrame(), tmp_path / "x.txt", tmp_path)
    assert (nb, nbb, sans) == (0, 0, [])


def test_donneurs_exposes_pour_depannage():
    """Le moteur expose les donneurs (surplus) ; ils se serialisent pour la
    proposition de depannage d'une demande urgente."""
    from stockflow.push_supabase import build_donor_rows
    today = pd.Timestamp("2026-07-13")
    # PARIS gros surplus sur la reference (donneur) ; LYON en tension
    stock = (
        "Code_Origine,BarCode V2,Taille,Total Stock,Marque Gp\n"
        f"PARIS,{REF},M,80,NIKE\nPARIS,{REF},L,80,NIKE\nPARIS,{REF},S,80,NIKE\n"
        f"LYON,{REF},M,2,NIKE\n"
    )
    dates = pd.date_range("2026-06-08", "2026-07-12", freq="3D")
    rows = []
    for d in dates:
        ds = d.strftime("%d/%m/%Y")
        rows.append(("PARIS", REF, "M", 1, 35.0, ds, "NIKE", "26 Q2", 35.0))
        rows.append(("LYON", REF, "M", 2, 70.0, ds, "NIKE", "26 Q2", 35.0))
    v = pd.DataFrame(rows, columns=[
        "Code_Origine", "BarCode V2", "Taille", "Total QteVenteRetail",
        "Total MtVenteRetailTTC", "Jours dans Date", "Marque Gp", "Saison", "PrixVente"])
    res, _ = run_analysis(stock=_bytes(stock), ventes=_bytes(v.to_csv(index=False)),
                          params=build_params(cible=14, seuil_score=50), today=today)
    assert not res.donors.empty
    donor_rows = build_donor_rows(res.donors)
    assert donor_rows
    # PARIS doit apparaitre comme donneur sur la reference, avec du surplus
    paris = [r for r in donor_rows if r["magasin"] == "PARIS" and r["reference"] == REF]
    assert paris
    assert all(set(["magasin", "reference", "taille", "qte_don", "couverture_j"]).issubset(r)
               for r in donor_rows)
    assert any(r["qte_don"] > 0 for r in paris)
