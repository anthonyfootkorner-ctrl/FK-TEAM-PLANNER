"""Tests de l'adaptateur donnees reelles (sizes + ingest_real)."""

import pandas as pd
import pytest

from stockflow.sizes import normalize_size, LETTRE, CHAUSSURE, ENFANT, AUTRE
from stockflow.ingest_real import split_barcode, load_real_dataset


def test_normalize_size_familles():
    assert normalize_size("  S ") == ("S", LETTRE)
    assert normalize_size("XXL") == ("XXL", LETTRE)
    assert normalize_size("TU") == ("TU", LETTRE)
    assert normalize_size("42") == ("42", CHAUSSURE)
    assert normalize_size("42,5") == ("42.5", CHAUSSURE)
    assert normalize_size("10/12 ANS") == ("10/12 ANS", ENFANT)
    assert normalize_size("24M") == ("24M", ENFANT)
    assert normalize_size("-")[1] == AUTRE
    assert normalize_size("")[0] == "?"


def test_split_barcode():
    ref, coul = split_barcode(pd.Series(["779229-04", "36N074-A9Y", "SANSDASH"]))
    assert list(ref) == ["779229", "36N074", "SANSDASH"]
    assert list(coul) == ["04", "A9Y", "UNI"]


def _write(tmp_path):
    stock = pd.DataFrame({
        "Code_Origine": ["PARIS", "PARIS", "LYON", "WEB"],
        "Marque Gp": ["NIKE", "NIKE", "NIKE", "NIKE"],
        "BarCode V2": ["779229-04", "779229-04", "779229-04", "779229-04"],
        "Taille": ["  S", "M", "L", "M"],
        "PrixAchat": ["30", "30", "30", "30"],
        "Total Stock": ["2", "50", "80", "40"],
    })
    # ventes : PARIS vend du S (rupture car stock faible) et une taille XL SANS stock
    sales = pd.DataFrame({
        "Jours dans Date": ["10/07/2026"] * 4,
        "Code_Origine": ["PARIS", "PARIS", "LYON", "PARIS"],
        "BarCode V2": ["779229-04", "779229-04", "779229-04", "779229-04"],
        "Taille": ["S", "M", "L", "XL"],
        "Marque Gp": ["NIKE"] * 4,
        "Saison": ["26 Q3"] * 4,
        "PrixVente": ["60", "60", "60", "60"],
        "Total QteVenteRetail": ["10", "3", "5", "4"],
        "Total MtVenteRetailTTC": ["600", "180", "300", "240"],
        "valeur prix d'achat": ["300", "90", "150", "120"],
    })
    sp = tmp_path / "stock.csv"; vp = tmp_path / "ventes.csv"
    stock.to_csv(sp, index=False); sales.to_csv(vp, index=False)
    return sp, vp


def test_load_real_dataset(tmp_path):
    sp, vp = _write(tmp_path)
    ds = load_real_dataset(sp, vp, today=pd.Timestamp("2026-07-13"))
    stocks, ventes, stores = ds["stocks"], ds["ventes"], ds["magasins"]

    # reference/couleur derives du barcode
    assert (stocks["reference"] == "779229").all()
    assert set(stocks["couleur"]) == {"04"}

    # prix de vente recupere depuis les ventes (60), pas seulement prix_achat
    assert (stocks["prix_vente"] == 60).all()

    # detection Web
    assert stocks.loc[stocks.magasin == "WEB", "indic_web"].all()
    assert not stocks.loc[stocks.magasin == "PARIS", "indic_web"].any()

    # recuperation de rupture : PARIS/XL vendu mais absent du stock -> ligne a 0
    paris_xl = stocks[(stocks.magasin == "PARIS") & (stocks.taille == "XL")]
    assert len(paris_xl) == 1
    assert paris_xl["stock_physique"].iloc[0] == 0

    # referentiel magasins minimal deduit
    assert set(stores["code_magasin"]) >= {"PARIS", "LYON", "WEB"}
    assert (stores.loc[stores.code_magasin == "WEB", "type_magasin"] == "WEB").all()


def test_app_service(tmp_path):
    import io
    from stockflow.app_service import build_params, run_analysis
    sp, vp = _write(tmp_path)
    params = build_params(cible=14, min_expediteur=10, min_web=14)
    assert params.get("couverture_cible_magasin") == 14
    # via buffers memoire (comme un upload navigateur)
    stock = io.BytesIO(open(sp, "rb").read())
    ventes = io.BytesIO(open(vp, "rb").read())
    res, ds = run_analysis(stock=stock, ventes=ventes, params=params,
                           today=pd.Timestamp("2026-07-13"))
    assert not res.blocked
    assert "stocks" in ds and not ds["stocks"].empty


def test_pipeline_sur_donnees_reelles(tmp_path):
    from stockflow.pipeline import run_pipeline
    from stockflow.parameters import Parameters
    sp, vp = _write(tmp_path)
    ds = load_real_dataset(sp, vp, today=pd.Timestamp("2026-07-13"))
    r = run_pipeline(preloaded=ds, params=Parameters(), today=pd.Timestamp("2026-07-13"))
    assert not r.blocked
    # PARIS/S est en quasi-rupture et vend fort -> doit recevoir un transfert
    if not r.transfers.empty:
        assert (r.transfers["expediteur"] != r.transfers["destinataire"]).all()
        sim = r.simulation_global.set_index("indicateur")
        assert sim.loc["stock_total", "avant"] == sim.loc["stock_total", "apres"]
