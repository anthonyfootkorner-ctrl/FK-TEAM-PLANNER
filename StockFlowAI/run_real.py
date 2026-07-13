"""Execution de StockFlow AI sur les exports reels (Fastmag).

Usage :
    python run_real.py --stock STOCK.csv --ventes VENTESTOCKFLOW.csv \
                       [--objectif OBJECTIF.csv] [--today 2026-07-13] \
                       [--export exports/reel.xlsx]

Utilise l'adaptateur :mod:`stockflow.ingest_real` (derive reference/couleur du
BarCode V2, standardise les tailles, deduit un referentiel magasins minimal).
Picking / historique absents => regles associees neutres (mode degrade,
reversible des que les fichiers sont fournis).
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

from stockflow import MOTEUR_VERSION
from stockflow.parameters import Parameters
from stockflow.pipeline import run_pipeline
from stockflow.ingest_real import load_real_dataset

ROOT = Path(__file__).resolve().parent


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="StockFlow AI sur donnees reelles")
    p.add_argument("--stock", required=True)
    p.add_argument("--ventes", required=True)
    p.add_argument("--objectif", default=None)
    p.add_argument("--reassort", default=None, help="fichier de reassorts programmes (xlsx)")
    p.add_argument("--config", default=str(ROOT / "config" / "parametres.xlsx"))
    p.add_argument("--today", default="2026-07-13")
    p.add_argument("--export", default=str(ROOT / "exports" / "stockflow_reel.xlsx"))
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
                        handlers=[logging.StreamHandler(sys.stdout)])
    log = logging.getLogger("stockflow")
    log.info("StockFlow AI v%s - donnees reelles", MOTEUR_VERSION)

    today = pd.Timestamp(args.today)
    log.info("Adaptation des exports reels...")
    datasets = load_real_dataset(args.stock, args.ventes, args.objectif,
                                 reassort_xlsx=args.reassort, today=today)
    for k, v in datasets.items():
        log.info("  %-11s : %d lignes", k, len(v))

    params = Parameters.load(args.config if Path(args.config).exists() else None)
    result = run_pipeline(preloaded=datasets, params=params, today=today,
                          export_path=Path(args.export))

    if result.blocked:
        log.error("Bloque : %s", result.message)
        for a in result.quality_report.anomalies:
            log.error("  - [%s] %s", a.fichier, a.message)
        return 2

    log.info("Transferts retenus : %d (%d iterations)", len(result.transfers),
             result.journal.get("nb_iterations"))
    log.info("Export : %s", result.export_path)

    # Fiche de revue epuree (pour validation par les equipes)
    from stockflow.exports import write_fiche_revue
    marque_map = {}
    st = datasets.get("stocks")
    if st is not None and not st.empty and "marque" in st.columns:
        marque_map = (st.drop_duplicates(["reference", "couleur"])
                        .set_index(["reference", "couleur"])["marque"].to_dict())
    fiche_path = Path(args.export).with_name(
        Path(args.export).stem.replace("stockflow", "fiche_revue") + ".xlsx")
    if "fiche_revue" not in fiche_path.name:
        fiche_path = Path(args.export).with_name("fiche_revue_" + Path(args.export).name)
    write_fiche_revue(fiche_path, result.transfers, marque_map=marque_map)
    log.info("Fiche de revue : %s", fiche_path)
    print("\n=== Simulation avant/apres ===")
    print(result.simulation_global.to_string(index=False))
    if not result.transfers.empty:
        cols = ["priorite", "score", "expediteur", "destinataire", "reference",
                "couleur", "taille", "quantite", "motif"]
        print("\n=== Top 15 transferts ===")
        print(result.transfers[[c for c in cols if c in result.transfers.columns]]
              .head(15).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
