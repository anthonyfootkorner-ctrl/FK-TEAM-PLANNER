"""Couche de service pour l'interface (mini-site) et les scripts.

Isole l'enchainement adaptateur -> moteur derriere une seule fonction, testable
independamment de Streamlit. Accepte aussi bien des chemins que des fichiers en
memoire (uploads navigateur), car pandas lit les deux.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple

import pandas as pd

from .parameters import Parameters
from .pipeline import run_pipeline, PipelineResult
from .ingest_real import load_real_dataset


def build_params(*, cible=14, min_expediteur=10, min_web=14, nb_max_destinations=4,
                 seuil_score=60, base: Optional[Parameters] = None) -> Parameters:
    """Construit un jeu de parametres a partir des reglages de l'interface."""
    p = base or Parameters()
    p.set("couverture_cible_magasin", int(cible))
    p.set("couverture_min_expediteur", int(min_expediteur))
    p.set("couverture_min_web", int(min_web))
    p.set("nb_max_destinations", int(nb_max_destinations))
    p.set("seuil_score_minimum", int(seuil_score))
    return p


def run_analysis(*, stock, ventes, reassort=None, objectif=None,
                 params: Optional[Parameters] = None,
                 today: Optional[pd.Timestamp] = None,
                 export_path: Optional[str | Path] = None) -> Tuple[PipelineResult, dict]:
    """Lance l'analyse complete sur des fichiers reels (chemins ou uploads).

    Retourne (resultat_pipeline, datasets_standardises).
    """
    today = pd.Timestamp(today) if today is not None else pd.Timestamp("2026-07-13")
    datasets = load_real_dataset(stock, ventes, objectif,
                                 reassort_xlsx=reassort, today=today)
    result = run_pipeline(preloaded=datasets, params=params or Parameters(),
                          today=today, export_path=export_path)
    return result, datasets
