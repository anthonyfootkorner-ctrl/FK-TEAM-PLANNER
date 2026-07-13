"""Tests des regles anti-erreur (module 5) et de la chaine complete."""

import pandas as pd
import pytest

from stockflow.parameters import Parameters
from stockflow.pipeline import run_pipeline
from stockflow import sample_data


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    d = tmp_path_factory.mktemp("data")
    paths = sample_data.write_all(d)
    result = run_pipeline(
        stocks_path=paths["stocks"].parent,
        sales_path=paths["ventes"].parent,
        picking_path=paths["picking"].parent,
        stores_path=paths["magasins"].parent,
        history_path=paths["historique"].parent,
        params=Parameters(),
        today=pd.Timestamp("2026-07-13"),
    )
    return result


def test_pipeline_non_bloque(demo):
    assert not demo.blocked
    assert demo.journal["statut"] == "OK"


def test_produit_des_transferts(demo):
    assert len(demo.transfers) > 0


def test_aucun_self_transfert(demo):
    t = demo.transfers
    assert (t.expediteur == t.destinataire).sum() == 0


def test_max_4_destinations(demo):
    t = demo.transfers
    dest = t.groupby("expediteur")["destinataire"].nunique()
    assert (dest <= 4).all()


def test_aucun_transfert_croise(demo):
    t = demo.transfers
    pairs = set(zip(t.expediteur, t.destinataire))
    assert not any((b, a) in pairs for (a, b) in pairs)


def test_aucun_stock_negatif(demo):
    t = demo.transfers
    assert (t.stock_exp_apres < 0).sum() == 0


def test_donneurs_physiques_conservent_20j(demo):
    t = demo.transfers
    phys = t[~t.is_web_don]
    # les donneurs physiques doivent conserver >= 20 jours de couverture
    assert (phys.cov_exp_apres < 20 - 1e-6).sum() == 0


def test_score_au_dessus_du_seuil(demo):
    t = demo.transfers
    assert (t.score >= 60).all()


def test_conservation_stock_total(demo):
    sim = demo.simulation_global.set_index("indicateur")
    assert sim.loc["stock_total", "avant"] == sim.loc["stock_total", "apres"]


def test_amelioration_reseau(demo):
    sim = demo.simulation_global.set_index("indicateur")
    # moins de ruptures et meilleur score de sante
    assert sim.loc["ruptures", "apres"] <= sim.loc["ruptures", "avant"]
    assert sim.loc["score_sante_reseau", "apres"] >= sim.loc["score_sante_reseau", "avant"]


def test_reproductibilite(demo, tmp_path):
    paths = sample_data.write_all(tmp_path)
    r2 = run_pipeline(
        stocks_path=paths["stocks"].parent, sales_path=paths["ventes"].parent,
        picking_path=paths["picking"].parent, stores_path=paths["magasins"].parent,
        history_path=paths["historique"].parent, params=Parameters(),
        today=pd.Timestamp("2026-07-13"),
    )
    # meme entree + memes parametres => meme nombre de transferts et meme score total
    assert len(r2.transfers) == len(demo.transfers)
    assert round(r2.transfers.score.sum(), 3) == round(demo.transfers.score.sum(), 3)


def test_cas_non_traites_present(demo):
    # l'onglet des cas non traites doit exister (meme vide)
    assert demo.cas_non_traites is not None


def test_blocage_donnees_incoherentes(tmp_path):
    # fichier stock sans colonne magasin => traitement bloque
    bad = tmp_path / "stocks"
    bad.mkdir()
    pd.DataFrame({"reference": ["R"], "couleur": ["N"], "taille": ["M"],
                  "stock_physique": [5]}).to_excel(bad / "s.xlsx", index=False)
    ventes = tmp_path / "ventes"
    ventes.mkdir()
    pd.DataFrame({"magasin": ["A"], "reference": ["R"], "couleur": ["N"],
                  "taille": ["M"], "ventes_35j": [3]}).to_excel(ventes / "v.xlsx", index=False)
    r = run_pipeline(stocks_path=bad, sales_path=ventes, params=Parameters(),
                     today=pd.Timestamp("2026-07-13"))
    assert r.blocked
