"""Couche de service pour l'interface (mini-site) et les scripts.

Isole l'enchainement adaptateur -> moteur derriere une seule fonction, testable
independamment de Streamlit. Accepte aussi bien des chemins que des fichiers en
memoire (uploads navigateur), car pandas lit les deux.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Optional, Tuple

import pandas as pd

from .parameters import Parameters
from .pipeline import run_pipeline, PipelineResult
from .ingest_real import load_real_dataset
from .reassort_central import compute_reassort_central, proposed_to_picking


def _buffer(src):
    """Bufferise une source (chemin ou fichier-memoire) en octets reutilisables.

    Le reassort central ET l'adaptateur StockFlow lisent tous deux les fichiers
    stock/ventes : un upload (flux) ne se lit qu'une fois, on met donc les
    octets en cache et on rend un ``BytesIO`` neuf a chaque appel."""
    if src is None:
        return None
    if isinstance(src, (bytes, bytearray)):
        data = bytes(src)
    elif hasattr(src, "read"):
        try:
            src.seek(0)
        except Exception:
            pass
        data = src.read()
    else:
        data = Path(src).read_bytes()

    def _factory():
        return io.BytesIO(data)

    return _factory


def build_params(*, cible=21, min_expediteur=30, min_web=14, nb_max_destinations=4,
                 seuil_score=60, base: Optional[Parameters] = None) -> Parameters:
    """Construit un jeu de parametres a partir des reglages de l'interface.

    Regles metier (validees) :
    * ``cible`` = couverture visee chez le RECEVEUR (jours) : appliquee aux
      transferts inter-magasins ET au reassort central (meme cible partout).
    * ``min_expediteur`` = couverture que l'EXPEDITEUR conserve apres envoi
      (jours) : il ne cede que le surplus au-dela de cette reserve.
    """
    p = base or Parameters()
    p.set("couverture_cible_magasin", int(cible))
    p.set("couverture_cible_central", int(cible))   # reassort central : meme cible receveur
    p.set("couverture_min_expediteur", int(min_expediteur))
    p.set("couverture_min_web", int(min_web))
    p.set("nb_max_destinations", int(nb_max_destinations))
    p.set("seuil_score_minimum", int(seuil_score))
    return p


def run_analysis(*, stock, ventes, reassort=None, objectif=None,
                 central_stock=None,
                 params: Optional[Parameters] = None,
                 today: Optional[pd.Timestamp] = None,
                 export_path: Optional[str | Path] = None) -> Tuple[PipelineResult, dict]:
    """Lance l'analyse complete sur des fichiers reels (chemins ou uploads).

    Enchainement « A + B » quand ``central_stock`` est fourni : on calcule
    d'abord le reassort central (CENTRAL -> boutiques), puis on injecte sa
    sortie comme *picking* (stock en transit) dans le moteur de transferts
    inter-magasins — qui calcule donc un besoin residuel NET du reassort central.
    Le detail du reassort central est renvoye dans ``datasets['reassort_central']``.

    Retourne (resultat_pipeline, datasets_standardises).
    """
    today = pd.Timestamp(today) if today is not None else pd.Timestamp("2026-07-13")
    params = params or Parameters()

    stock_buf = _buffer(stock)
    ventes_buf = _buffer(ventes)
    central_buf = _buffer(central_stock)

    reassort_central_res = None
    picking_override = None
    if central_buf is not None:
        reassort_central_res = compute_reassort_central(
            stock=stock_buf(), ventes=ventes_buf(), central_stock=central_buf(),
            params=params,
        )
        picking_override = proposed_to_picking(reassort_central_res.proposed)

    datasets = load_real_dataset(stock_buf(), ventes_buf(), objectif,
                                 reassort_xlsx=reassort, today=today)

    # Chainage : le reassort central prime sur un eventuel fichier reassort
    # importe — c'est lui le stock en transit officiel de la semaine.
    if picking_override is not None:
        datasets["picking"] = picking_override
    if reassort_central_res is not None:
        datasets["reassort_central"] = reassort_central_res.proposed
        datasets["reassort_central_result"] = reassort_central_res

    result = run_pipeline(preloaded=datasets, params=params,
                          today=today, export_path=export_path)
    return result, datasets
