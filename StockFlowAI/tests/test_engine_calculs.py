"""Validation des calculs (brief Etape 2) sur un echantillon controle.

Chaque valeur attendue est calculee a la main pour garantir 100% de
concordance sur l'echantillon, comme exige par le critere de validation.
"""

import numpy as np
import pandas as pd
import pytest

from stockflow.parameters import Parameters
from stockflow import projected_stock, sales_metrics, coverage as coverage_mod
from stockflow.size_grids import GridIndex


@pytest.fixture
def params():
    return Parameters()


@pytest.fixture
def stores():
    return pd.DataFrame([
        {"code_magasin": "A", "ville": "Paris", "flagship": False, "actif": True},
        {"code_magasin": "B", "ville": "Lyon", "flagship": False, "actif": True},
        {"code_magasin": "WEB", "ville": "Entrepot", "type_magasin": "WEB", "actif": True},
    ])


@pytest.fixture
def stocks():
    return pd.DataFrame([
        # magasin A : S peu de stock, M bien fourni, L en rupture
        {"magasin": "A", "ville": "Paris", "reference": "R1", "couleur": "N", "taille": "S",
         "stock_physique": 3, "stock_disponible": 3, "categorie": "TEXTILE_HOMME",
         "prix_vente": 50, "indic_web": False, "indic_picking": False},
        {"magasin": "A", "ville": "Paris", "reference": "R1", "couleur": "N", "taille": "M",
         "stock_physique": 30, "stock_disponible": 30, "categorie": "TEXTILE_HOMME",
         "prix_vente": 50, "indic_web": False, "indic_picking": False},
        {"magasin": "A", "ville": "Paris", "reference": "R1", "couleur": "N", "taille": "L",
         "stock_physique": 0, "stock_disponible": 0, "categorie": "TEXTILE_HOMME",
         "prix_vente": 50, "indic_web": False, "indic_picking": False},
        # magasin B : donneur potentiel sur S
        {"magasin": "B", "ville": "Lyon", "reference": "R1", "couleur": "N", "taille": "S",
         "stock_physique": 100, "stock_disponible": 100, "categorie": "TEXTILE_HOMME",
         "prix_vente": 50, "indic_web": False, "indic_picking": False},
        # WEB
        {"magasin": "WEB", "ville": "Entrepot", "reference": "R1", "couleur": "N", "taille": "L",
         "stock_physique": 50, "stock_disponible": 50, "categorie": "TEXTILE_HOMME",
         "prix_vente": 50, "indic_web": True, "indic_picking": False},
    ])


@pytest.fixture
def sales():
    return pd.DataFrame([
        {"magasin": "A", "reference": "R1", "couleur": "N", "taille": "S",
         "ventes_35j": 35, "ventes_7j": 7, "ca_35j": 1750, "ca_7j": 350},
        {"magasin": "A", "reference": "R1", "couleur": "N", "taille": "M",
         "ventes_35j": 35, "ventes_7j": 7, "ca_35j": 1750, "ca_7j": 350},
        {"magasin": "A", "reference": "R1", "couleur": "N", "taille": "L",
         "ventes_35j": 7, "ventes_7j": 4, "ca_35j": 350, "ca_7j": 200},
        {"magasin": "B", "reference": "R1", "couleur": "N", "taille": "S",
         "ventes_35j": 35, "ventes_7j": 7, "ca_35j": 1750, "ca_7j": 350},
    ])


@pytest.fixture
def picking():
    # reassort deja programme : +15 M pour le magasin A (statut non receptionne)
    return pd.DataFrame([
        {"magasin": "A", "reference": "R1", "couleur": "N", "taille": "M",
         "quantite_prevue": 15, "statut_reassort": "PREPARE", "id_mouvement": "PK1"},
        # un reassort deja receptionne ne doit PAS compter en transit
        {"magasin": "A", "reference": "R1", "couleur": "N", "taille": "S",
         "quantite_prevue": 99, "statut_reassort": "RECEPTIONNE", "id_mouvement": "PK2"},
    ])


def build(stocks, sales, picking, stores, params):
    base = projected_stock.build_base(stocks, picking, stores, params)
    base = sales_metrics.attach_sales(base, sales, params, pd.Timestamp("2026-07-13"))
    base = coverage_mod.compute_coverage(base, params)
    return base


def get(base, mag, taille):
    row = base[(base.magasin == mag) & (base.taille == taille)].iloc[0]
    return row


def test_stock_projete_integre_picking_en_transit(stocks, sales, picking, stores, params):
    base = build(stocks, sales, picking, stores, params)
    m = get(base, "A", "M")
    assert m["stock_actuel"] == 30
    assert m["stock_transit"] == 15  # picking prepare
    assert m["stock_projete"] == 45  # 30 + 15


def test_picking_receptionne_non_compte_en_transit(stocks, sales, picking, stores, params):
    base = build(stocks, sales, picking, stores, params)
    s = get(base, "A", "S")
    assert s["stock_transit"] == 0  # le PK2 receptionne ne compte pas
    assert s["stock_projete"] == 3


def test_couverture_formule(stocks, sales, picking, stores, params):
    base = build(stocks, sales, picking, stores, params)
    # M : daily = 35/35 = 1 ; couverture projetee = 45/1 = 45
    m = get(base, "A", "M")
    assert m["moyenne_quotidienne"] == pytest.approx(1.0)
    assert m["couverture_projetee"] == pytest.approx(45.0)
    # S : daily 1, projetee 3/1 = 3
    s = get(base, "A", "S")
    assert s["couverture_projetee"] == pytest.approx(3.0)


def test_besoin_residuel_net_du_picking(stocks, sales, picking, stores, params):
    base = build(stocks, sales, picking, stores, params)
    # S : cible 30j * daily 1 = 30 ; projete 3 => besoin residuel 27
    s = get(base, "A", "S")
    assert s["besoin_residuel"] == 27
    # M : cible 30 ; projete 45 => aucun besoin (anti-double reassort)
    m = get(base, "A", "M")
    assert m["besoin_residuel"] == 0


def test_couverture_cas_sans_vente(stores, params):
    stocks = pd.DataFrame([
        {"magasin": "A", "ville": "Paris", "reference": "R9", "couleur": "N", "taille": "M",
         "stock_physique": 10, "stock_disponible": 10, "categorie": "TEXTILE_HOMME", "prix_vente": 10},
        {"magasin": "A", "ville": "Paris", "reference": "R9", "couleur": "N", "taille": "L",
         "stock_physique": 0, "stock_disponible": 0, "categorie": "TEXTILE_HOMME", "prix_vente": 10},
    ])
    sales = pd.DataFrame(columns=["magasin", "reference", "couleur", "taille", "ventes_35j", "ventes_7j"])
    base = build(stocks, sales, pd.DataFrame(), stores, params)
    m = get(base, "A", "M")  # stock>0 sans vente -> dormant 999
    assert m["couverture_projetee"] == 999
    l = get(base, "A", "L")  # stock 0 sans vente -> 0
    assert l["couverture_projetee"] == 0


def test_web_detecte(stocks, sales, picking, stores, params):
    base = build(stocks, sales, picking, stores, params)
    assert base[base.magasin == "WEB"]["is_web"].all()
    assert not base[base.magasin == "A"]["is_web"].any()


def test_grille_avant_apres(stocks, sales, picking, stores, params):
    base = build(stocks, sales, picking, stores, params)
    idx = GridIndex.from_frame(base, params)
    # A/R1/N : S(3), M(30), L(0) -> tailles dispo S,M ; coeur S,M => 2 coeur, valide
    st = idx.state("A", "R1", "N")
    assert set(st.tailles_dispo) == {"S", "M"}
    assert st.nb_coeur == 2
    assert st.valide
    # apres ajout de L : grille S,M,L -> 3 coeur
    st2 = idx.state_after_add("A", "R1", "N", "L", 5)
    assert st2.nb_coeur == 3
