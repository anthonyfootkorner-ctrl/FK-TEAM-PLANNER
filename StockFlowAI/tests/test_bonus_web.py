"""Priorisation du rechargement WEB via un bonus de score.

Le web (canal en ligne, plus gros CA) capte le surplus avant les magasins :
un candidat dont le RECEVEUR est le web reçoit un bonus additif
``bonus_web_receveur`` sur son score, ce qui le fait servir plus tôt (avant que
les donneurs n'épuisent leur surplus / leur quota de destinations).
"""

from __future__ import annotations

import pytest

from stockflow.parameters import Parameters
from stockflow.transfer_scoring import TransferScorer, Candidate


def _cand(is_web_rec: bool) -> Candidate:
    return Candidate(
        expediteur="A", destinataire="WEB" if is_web_rec else "B",
        reference="R", couleur="", taille="M", qte=1.0,
        is_web_don=False,
        cov_don_avant=40.0, cov_don_apres=35.0, daily_don=1.0,
        grid_don_avant="M", grid_don_apres="M", grid_don_valide_apres=True,
        cov_rec_avant=0.0, cov_rec_apres=21.0, daily_rec=1.0, tendance_rec="stable",
        grid_rec_coeur_avant=1, grid_rec_coeur_apres=2,
        grid_rec_avant="S", grid_rec_apres="M/S", type_besoin="couverture",
        distance_km=100.0, flagship_rec=False, criticite_rec=0.5,
        dans_top30=False, destination_deja_ouverte=False, penalite_historique=0.0,
        is_web_rec=is_web_rec)


def test_le_web_recoit_un_bonus_de_score():
    p = Parameters()
    p.set("bonus_web_receveur", 8)
    s = TransferScorer(p)
    sc_web = s.score(_cand(True)).score
    sc_mag = s.score(_cand(False)).score
    # meme candidat, seule la destination change : le web est mieux noté
    assert sc_web > sc_mag
    assert sc_web - sc_mag == pytest.approx(8, abs=0.2)


def test_bonus_zero_pas_de_difference():
    p = Parameters()
    p.set("bonus_web_receveur", 0)
    s = TransferScorer(p)
    assert s.score(_cand(True)).score == s.score(_cand(False)).score
