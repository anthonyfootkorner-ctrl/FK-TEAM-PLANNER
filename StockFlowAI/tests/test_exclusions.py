"""Tests des references a exclure des reassorts.

Verifie que :
* le chargeur ``parse_exclusions`` lit txt / csv / xlsx et une colonne ou la 1re ;
* ``excluded_mask`` matche la reference exacte ET le modele (partie avant tiret) ;
* de bout en bout (``run_analysis``), une reference exclue ne bouge NULLE PART :
  ni reassort central, ni picking/Fastmag, ni transfert inter-magasins — tandis
  qu'une autre reference non exclue continue de circuler normalement.
"""

from __future__ import annotations

import io

import pandas as pd

from stockflow.app_service import run_analysis, build_params
from stockflow.exclusions import parse_exclusions, excluded_mask, to_set

REF = "0200NZ-010"     # exclue dans les tests de bout en bout
REF2 = "0200NZ-020"    # conservee (meme modele, autre couleur) -> NE PAS exclure par defaut
REF3 = "9999XX-000"    # conservee (autre modele)


# ---------------------------------------------------------------------------
# Chargement de la liste
# ---------------------------------------------------------------------------
def test_parse_txt_une_ref_par_ligne():
    data = f"{REF}\n{REF3}\n\n".encode("utf-8")
    assert parse_exclusions(data) == [REF, REF3]


def test_parse_txt_separateurs_virgule_pv():
    data = f"{REF}; {REF3}, 0200NZ".encode("utf-8")
    got = parse_exclusions(data)
    assert set(got) == {REF, REF3, "0200NZ"}


def test_parse_csv_colonne_reference():
    csv = f"Marque,Référence,Note\nNIKE,{REF},promo\nADIDAS,{REF3},fin de serie\n"
    assert parse_exclusions(csv.encode("utf-8")) == [REF, REF3]


def test_parse_xlsx_premiere_colonne_si_pas_de_nom_connu():
    df = pd.DataFrame({"codes": [REF, REF3, REF]})   # nom inconnu -> 1re colonne
    buf = io.BytesIO()
    df.to_excel(buf, index=False)
    assert parse_exclusions(buf.getvalue()) == [REF, REF3]   # dedupe, ordre stable


def test_parse_vide_ou_none():
    assert parse_exclusions(None) == []
    assert parse_exclusions(b"") == []


# ---------------------------------------------------------------------------
# Masque
# ---------------------------------------------------------------------------
def test_mask_reference_exacte():
    s = pd.Series([REF, REF2, REF3])
    m = excluded_mask(s, [REF])
    assert list(m) == [True, False, False]


def test_mask_modele_exclut_toutes_couleurs():
    s = pd.Series([REF, REF2, REF3])
    m = excluded_mask(s, ["0200NZ"])          # modele seul
    assert list(m) == [True, True, False]


def test_mask_normalise_casse_espaces():
    s = pd.Series([REF])
    assert list(excluded_mask(s, [f"  {REF.lower()}  "])) == [True]


def test_to_set_ignore_vides():
    assert to_set([REF, "", None, "nan", " "]) == {REF}


# ---------------------------------------------------------------------------
# Bout en bout
# ---------------------------------------------------------------------------
def _stock_csv():
    rows = ["Code_Origine,BarCode V2,Taille,Total Stock,Marque Gp"]
    for ref in (REF, REF2):
        rows += [f"LYON,{ref},M,1,NIKE", f"LYON,{ref},L,4,NIKE", f"LYON,{ref},S,3,NIKE",
                 f"PARIS,{ref},M,60,NIKE", f"PARIS,{ref},L,60,NIKE", f"PARIS,{ref},S,60,NIKE"]
    return "\n".join(rows) + "\n"


def _ventes_csv():
    dates = pd.date_range("2026-06-08", "2026-07-12", freq="3D")
    rows = []
    for d in dates:
        ds = d.strftime("%d/%m/%Y")
        for ref in (REF, REF2):
            for t, q in (("M", 2), ("L", 1), ("S", 1)):
                rows.append(("LYON", ref, t, q, 35.0 * q, ds, "NIKE", "26 Q2", 35.0))
            rows.append(("PARIS", ref, "M", 1, 35.0, ds, "NIKE", "26 Q2", 35.0))
    v = pd.DataFrame(rows, columns=[
        "Code_Origine", "BarCode V2", "Taille", "Total QteVenteRetail",
        "Total MtVenteRetailTTC", "Jours dans Date", "Marque Gp", "Saison", "PrixVente"])
    return v.to_csv(index=False)


def _central_tsv():
    rows = ["Référence\tCouleur\tTaille\tStock\tMagasin"]
    for ref in (REF, REF2):
        rows += [f"{ref}\tNOIR\tM\t100\tCENTRAL", f"{ref}\tNOIR\tL\t50\tCENTRAL",
                 f"{ref}\tNOIR\tS\t50\tCENTRAL"]
    return ("\n".join(rows) + "\n").encode("latin1")


def _bytes(s):
    return io.BytesIO(s.encode("utf-8"))


def test_reference_exclue_ne_bouge_nulle_part():
    today = pd.Timestamp("2026-07-13")
    params = build_params(cible=14, seuil_score=50, exclude_refs=[REF])
    result, ds = run_analysis(
        stock=_bytes(_stock_csv()), ventes=_bytes(_ventes_csv()),
        central_stock=_central_tsv(), params=params, today=today)

    # 1) reassort central : REF absente, REF2 presente
    rc = ds["reassort_central"]
    refs_rc = set(rc["barcode"].astype(str)) if not rc.empty else set()
    assert REF not in refs_rc
    assert REF2 in refs_rc

    # 2) picking (=> Fastmag) : REF absente
    pick = ds["picking"]
    assert (pick["reference"] != REF).all()

    # 3) transferts inter-magasins : REF absente, REF2 peut circuler
    t = result.transfers
    if t is not None and not t.empty:
        assert (t["reference"] != REF).all()


def test_sans_exclusion_la_reference_circule():
    """Controle : sans liste d'exclusion, REF apparait bien quelque part."""
    today = pd.Timestamp("2026-07-13")
    params = build_params(cible=14, seuil_score=50)
    _, ds = run_analysis(
        stock=_bytes(_stock_csv()), ventes=_bytes(_ventes_csv()),
        central_stock=_central_tsv(), params=params, today=today)
    rc = ds["reassort_central"]
    assert REF in set(rc["barcode"].astype(str))
