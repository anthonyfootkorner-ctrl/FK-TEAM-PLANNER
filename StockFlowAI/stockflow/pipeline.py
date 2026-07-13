"""Orchestration du moteur StockFlow AI (modules 1 a 10 + sorties).

Enchaine : import -> controle qualite -> stock projete -> ventes/couvertures
-> grilles -> donneurs/receveurs -> criticite -> optimisation -> simulation
-> implantations -> exports, en journalisant chaque etape.

La fonction :func:`run_pipeline` est reproductible : memes fichiers + memes
parametres -> memes resultats (aucune source d'aleatoire).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

import pandas as pd

from . import (
    MOTEUR_VERSION,
    schema,
    import_data,
    quality_checks as qc,
    projected_stock,
    sales_metrics,
    coverage as coverage_mod,
    size_grids,
    donors as donors_mod,
    receivers as receivers_mod,
    store_criticality,
    optimizer as optimizer_mod,
    simulation as simulation_mod,
    implantation as implantation_mod,
    exports,
)
from .geo import DistanceMatrix
from .parameters import Parameters


logger = logging.getLogger("stockflow")


@dataclass
class PipelineResult:
    export_path: Optional[Path] = None
    transfers: pd.DataFrame = field(default_factory=pd.DataFrame)
    flux: pd.DataFrame = field(default_factory=pd.DataFrame)
    simulation_global: pd.DataFrame = field(default_factory=pd.DataFrame)
    simulation_stores: pd.DataFrame = field(default_factory=pd.DataFrame)
    implantations: pd.DataFrame = field(default_factory=pd.DataFrame)
    cas_non_traites: pd.DataFrame = field(default_factory=pd.DataFrame)
    quality_report: Optional[qc.QualityReport] = None
    journal: Dict = field(default_factory=dict)
    base: pd.DataFrame = field(default_factory=pd.DataFrame)
    blocked: bool = False
    message: str = ""


def run_pipeline(*, stocks_path=None, sales_path=None, picking_path=None, stores_path=None,
                 history_path=None, params: Optional[Parameters] = None,
                 distances_path=None, today: Optional[pd.Timestamp] = None,
                 export_path=None, preloaded: Optional[Dict[str, pd.DataFrame]] = None) -> PipelineResult:
    t0 = time.time()
    params = params or Parameters()
    today = pd.Timestamp(today) if today is not None else pd.Timestamp("2026-07-13")

    journal: Dict = {
        "date_execution": str(today.date()),
        "version_moteur": MOTEUR_VERSION,
        "source_parametres": params.source,
    }

    # --- Module 1 : import ---
    if preloaded is not None:
        # donnees deja standardisees (ex. adaptateur ingest_real) : on saute la
        # lecture Excel mais on garde le controle qualite.
        logger.info("Donnees pre-chargees (adaptateur).")
        stocks = schema.map_columns(preloaded.get("stocks", pd.DataFrame()))
        sales = schema.map_columns(preloaded.get("ventes", pd.DataFrame()))
        picking = schema.map_columns(preloaded.get("picking", pd.DataFrame()))
        stores = schema.map_columns(preloaded.get("magasins", pd.DataFrame()))
        history = schema.map_columns(preloaded.get("historique", pd.DataFrame()))
    else:
        logger.info("Import des fichiers...")
        stocks = import_data.load_stocks(stocks_path)
        sales = import_data.load_sales(sales_path)
        picking = import_data.load_picking(picking_path) if picking_path else pd.DataFrame()
        stores = import_data.load_stores(stores_path) if stores_path else pd.DataFrame()
        history = import_data.load_history(history_path) if history_path else pd.DataFrame()

    # Magasins fermes/inactifs : retires ENTIEREMENT du jeu de donnees (stock,
    # ventes, etc.). Utile quand l'export contient des lignes fantomes pour un
    # magasin ferme. Les reserves externes (magasins_exclus_flux, ex. CENTRAL)
    # ne sont PAS retirees ici : elles restent dans les donnees mais hors flux.
    inactifs = {str(x).strip().upper() for x in params.get("magasins_inactifs", []) or []}
    if inactifs:
        def _drop(df, col):
            if df is not None and not df.empty and col in df.columns:
                return df[~df[col].astype(str).str.upper().isin(inactifs)].copy()
            return df
        stocks = _drop(stocks, "magasin")
        sales = _drop(sales, "magasin")
        picking = _drop(picking, "magasin")
        history = _drop(_drop(history, "expediteur"), "destinataire")
        stores = _drop(stores, "code_magasin")
        journal["magasins_inactifs_retires"] = ", ".join(sorted(inactifs))

    report = qc.QualityReport()
    stocks = qc.check_stocks(stocks, report)
    sales = qc.check_sales(sales, report)
    picking = qc.check_picking(picking, report)
    stores = qc.check_stores(stores, report)
    history = qc.check_history(history, report)
    qc.build_summary({"stocks": stocks, "ventes": sales, "picking": picking,
                      "magasins": stores, "historique": history}, report)

    journal["fichiers_charges"] = ", ".join([
        f"stocks({len(stocks)})", f"ventes({len(sales)})", f"picking({len(picking)})",
        f"magasins({len(stores)})", f"historique({len(history)})",
    ])
    journal["nb_anomalies"] = len(report.anomalies)

    if report.bloquant:
        logger.error("Traitement bloque : donnees incoherentes.")
        journal["statut"] = "BLOQUE"
        journal["duree_s"] = round(time.time() - t0, 2)
        return PipelineResult(quality_report=report, journal=journal, blocked=True,
                              message="Traitement bloque : colonnes essentielles manquantes.")

    # --- Module 2 : stock projete ---
    logger.info("Calcul des stocks projetes...")
    base = projected_stock.build_base(stocks, picking, stores, params)
    web_codes = projected_stock.web_store_codes(stores, stocks, params)

    # --- Module 3 : ventes + couvertures ---
    logger.info("Calcul des ventes, tendances et couvertures...")
    base = sales_metrics.attach_sales(base, sales, params, today)
    base = coverage_mod.compute_coverage(base, params)

    # --- Module 4 : grilles ---
    logger.info("Analyse des grilles de tailles...")
    grid_index = size_grids.GridIndex.from_frame(base, params, stock_col="stock_actuel")
    base = size_grids.annotate_grids(base, grid_index)

    # --- Modules 7 & 8 : top 30 + criticite ---
    logger.info("Top references et indice de criticite...")
    top = store_criticality.compute_top_references(base, params)
    criticite = store_criticality.compute_store_criticality(base, top, stores, params, web_codes)

    # --- Modules 5 & 6 : donneurs / receveurs ---
    logger.info("Detection donneurs / receveurs...")
    donors = donors_mod.detect_donors(base, params, web_codes, history, today)
    needs = receivers_mod.detect_receivers(base, grid_index, params, web_codes)

    # --- Module 10 : optimisation ---
    logger.info("Optimisation iterative...")
    distance = DistanceMatrix.load(params, distances_path)
    opt = optimizer_mod.Optimizer(base, needs, donors, top, criticite, stores,
                                  grid_index, distance, params, history, today)
    # gros volume : passe rapide (pre-scoring + faisabilite) pour rester dans
    # des temps de calcul acceptables ; petit volume : boucle iterative fidele.
    fast = len(base) > 20000 or len(needs) > 3000
    result = opt.run(fast=fast)
    journal["mode_optimisation"] = "rapide" if fast else "iteratif"
    journal["nb_iterations"] = result.iterations
    journal["nb_transferts_retenus"] = 0 if result.transfers is None else len(result.transfers)

    # --- Simulation avant/apres ---
    logger.info("Simulation avant/apres...")
    # regenerer une grille "avant" (l'index a ete mute par l'optimiseur)
    grid_before = size_grids.GridIndex.from_frame(base, params, stock_col="stock_actuel")
    sim_global, sim_stores = simulation_mod.simulate(base, result, params, web_codes)

    # --- Implantations ---
    logger.info("Propositions d'implantation...")
    implantations = implantation_mod.propose_implantations(base, stores, params, web_codes)

    # --- Sorties agregees ---
    flux = exports.build_flux_summary(result.transfers, base, params)
    cas = exports.build_cas_non_traites(result, opt.needs, report, base, web_codes)

    journal["duree_s"] = round(time.time() - t0, 2)
    journal["statut"] = "OK"
    journal["parametres_cles"] = (
        f"cible={params.get('couverture_cible_magasin')}j, "
        f"min_exp={params.get('couverture_min_expediteur')}j, "
        f"min_web={params.get('couverture_min_web')}j, "
        f"max_dest={params.get('nb_max_destinations')}, "
        f"seuil_score={params.get('seuil_score_minimum')}"
    )

    export_path_result = None
    if export_path is not None:
        logger.info("Export Excel...")
        export_path_result = exports.export_excel(
            export_path,
            transfers=result.transfers,
            flux=flux,
            simulation_global=sim_global,
            simulation_stores=sim_stores,
            implantations=implantations,
            cas_non_traites=cas,
            parametres=params.to_dataframe(),
            journal=exports.build_journal(journal),
            top_references=top,
            criticite=criticite,
        )

    return PipelineResult(
        export_path=export_path_result,
        transfers=result.transfers if result.transfers is not None else pd.DataFrame(),
        flux=flux,
        simulation_global=sim_global,
        simulation_stores=sim_stores,
        implantations=implantations,
        cas_non_traites=cas,
        quality_report=report,
        journal=journal,
        base=base,
        blocked=False,
        message="OK",
    )
