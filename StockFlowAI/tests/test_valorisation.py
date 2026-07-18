"""Tests de la valorisation cumulative des reassorts."""

from __future__ import annotations

import pandas as pd

from stockflow.valorisation import (
    build_new_cohorts, accumulate, summarize, cohorts_to_close, CENTRAL,
)


def _ventes(rows):
    return pd.DataFrame(rows, columns=["magasin", "reference", "qte", "ca", "date"]).assign(
        date=lambda d: pd.to_datetime(d["date"]))


def test_build_cohorts_central_et_interstore():
    rc = pd.DataFrame({"boutique": ["LYON", "LYON", "PARIS"],
                       "barcode": ["REF1", "REF1", "REF2"],
                       "qte_proposee": [3, 2, 4]})
    transfers = [{"expediteur": "PARIS", "destinataire": "LYON", "reference": "REF9", "quantite": 5}]
    cohorts = build_new_cohorts("run1", "2026-07-13", rc, transfers)
    central = [c for c in cohorts if c["type"] == "central"]
    inter = [c for c in cohorts if c["type"] == "interstore"]
    # central : LYON/REF1 agrege 3+2=5, PARIS/REF2=4
    lyon = next(c for c in central if c["destinataire"] == "LYON" and c["reference"] == "REF1")
    assert lyon["sent_qty"] == 5 and lyon["expediteur"] == CENTRAL
    assert next(c for c in central if c["destinataire"] == "PARIS")["sent_qty"] == 4
    # interstore : credite l'expediteur PARIS
    assert inter and inter[0]["expediteur"] == "PARIS" and inter[0]["sent_qty"] == 5


def test_accumulate_plafonne_et_ferme():
    # cohorte : CENTRAL a envoye 10 REF1 a LYON le 13/07
    coh = build_new_cohorts("run1", "2026-07-13",
                            pd.DataFrame({"boutique": ["LYON"], "barcode": ["REF1"], "qte_proposee": [10]}),
                            [])
    coh = [dict(c, id=1) for c in coh]
    stocks = pd.DataFrame({"reference": ["REF1"], "prix_achat": [10.0]})

    # semaine 1 : 4 ventes a LYON sur REF1 (prix ~30 TTC)
    v1 = _ventes([("LYON", "REF1", 4, 120.0, "2026-07-16")])
    up1 = accumulate(coh, v1, stocks)
    assert len(up1) == 1
    r = up1[0]
    assert r["cumul_units"] == 4 and not r["closed"]
    assert r["cumul_ca"] == 120.0            # 4 x 30
    # marge = 4 x (30/1.2 - 10) = 4 x 15 = 60
    assert r["cumul_marge"] == 60.0
    assert r["last_date"] == "2026-07-16"

    # semaine 2 : 8 ventes de plus -> plafonne a 10 (reste 6), ferme
    v2 = _ventes([("LYON", "REF1", 8, 240.0, "2026-07-23")])
    up2 = accumulate(up1, v2, stocks)
    r2 = up2[0]
    assert r2["cumul_units"] == 10 and r2["closed"] is True     # plafond
    # +6 unites attribuees a 30 => +180 CA
    assert r2["cumul_ca"] == 300.0
    assert r2["cumul_marge"] == 150.0        # 10 x 15


def test_pas_de_double_comptage_fenetre_recouvrante():
    coh = build_new_cohorts("run1", "2026-07-13",
                            pd.DataFrame({"boutique": ["LYON"], "barcode": ["REF1"], "qte_proposee": [10]}),
                            [])
    coh = [dict(c, id=1) for c in coh]
    stocks = pd.DataFrame({"reference": ["REF1"], "prix_achat": [10.0]})
    v1 = _ventes([("LYON", "REF1", 3, 90.0, "2026-07-16")])
    up1 = accumulate(coh, v1, stocks)
    # meme fichier rejoue (recouvrement) : last_date deja au 16 -> 0 ajout
    up_again = accumulate(up1, v1, stocks)
    # aucune cohorte modifiee (rien de neuf apres last_date)
    assert all(u["cumul_units"] == 3 for u in up_again) or up_again == []


def test_credit_expediteur_dans_summarize():
    transfers = [{"expediteur": "PARIS", "destinataire": "LYON", "reference": "REF1", "quantite": 5}]
    coh = build_new_cohorts("run1", "2026-07-13", None, transfers)
    coh = [dict(c, id=1) for c in coh]
    stocks = pd.DataFrame({"reference": ["REF1"], "prix_achat": [10.0]})
    v = _ventes([("LYON", "REF1", 5, 150.0, "2026-07-16")])
    up = accumulate(coh, v, stocks)
    s = summarize(up)
    # l'inter-magasins credite l'expediteur PARIS
    assert s["interstore"]["par_expediteur"]["PARIS"]["units"] == 5
    assert s["interstore"]["par_expediteur"]["PARIS"]["ca"] == 150
    assert s["central"]["units"] == 0


def test_cohorts_to_close_remplace_meme_cle():
    existing = [{"id": 7, "type": "central", "destinataire": "LYON", "reference": "REF1"}]
    new = build_new_cohorts("run2", "2026-07-20",
                            pd.DataFrame({"boutique": ["LYON"], "barcode": ["REF1"], "qte_proposee": [4]}),
                            [])
    assert cohorts_to_close(new, existing) == [7]
