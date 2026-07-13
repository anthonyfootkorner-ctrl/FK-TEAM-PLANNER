"""Point d'entree StockFlow AI (V1).

Usage :
    python main.py                       # utilise les fichiers de data/ (ou demo)
    python main.py --demo                # genere un jeu de demo puis execute
    python main.py --config config/parametres.xlsx
    python main.py --stocks data/stocks --ventes data/ventes ...

Le moteur ne fait que RECOMMANDER : aucun transfert n'est execute.
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
from stockflow import sample_data


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
EXPORTS = ROOT / "exports"
LOGS = ROOT / "logs"
CONFIG = ROOT / "config"


def setup_logging() -> None:
    LOGS.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(LOGS / "stockflow.log", encoding="utf-8"),
        ],
    )


def _first_dir_with_files(d: Path) -> Path | None:
    if d.is_dir() and any(d.glob("*.xlsx")):
        return d
    return None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="StockFlow AI - moteur de recommandation de transferts")
    parser.add_argument("--demo", action="store_true", help="generer un jeu de demonstration")
    parser.add_argument("--config", default=str(CONFIG / "parametres.xlsx"))
    parser.add_argument("--stocks", default=str(DATA / "stocks"))
    parser.add_argument("--ventes", default=str(DATA / "ventes"))
    parser.add_argument("--picking", default=str(DATA / "picking"))
    parser.add_argument("--magasins", default=str(DATA / "magasins"))
    parser.add_argument("--historique", default=str(DATA / "historique"))
    parser.add_argument("--distances", default=str(CONFIG / "distances.xlsx"))
    parser.add_argument("--today", default="2026-07-13")
    parser.add_argument("--export", default=None)
    args = parser.parse_args(argv)

    setup_logging()
    log = logging.getLogger("stockflow")
    log.info("StockFlow AI v%s", MOTEUR_VERSION)

    if args.demo or _first_dir_with_files(Path(args.stocks)) is None:
        log.info("Generation d'un jeu de donnees de demonstration...")
        sample_data.write_all(DATA)

    params = Parameters.load(args.config if Path(args.config).exists() else None)
    # ecrire un modele de parametres si absent (versionnement des seuils)
    if not Path(args.config).exists():
        params.save_template(CONFIG / "parametres.xlsx")
        log.info("Modele de parametres ecrit : %s", CONFIG / "parametres.xlsx")

    export_path = Path(args.export) if args.export else EXPORTS / f"stockflow_{args.today}.xlsx"

    result = run_pipeline(
        stocks_path=args.stocks,
        sales_path=args.ventes,
        picking_path=args.picking,
        stores_path=args.magasins,
        history_path=args.historique,
        params=params,
        distances_path=args.distances if Path(args.distances).exists() else None,
        today=pd.Timestamp(args.today),
        export_path=export_path,
    )

    if result.blocked:
        log.error("Execution bloquee : %s", result.message)
        for a in result.quality_report.anomalies:
            log.error("  - [%s] %s", a.fichier, a.message)
        return 2

    log.info("Transferts retenus : %d", len(result.transfers))
    log.info("Iterations : %s", result.journal.get("nb_iterations"))
    log.info("Export : %s", result.export_path)

    # apercu console
    if not result.transfers.empty:
        cols = ["priorite", "score", "expediteur", "destinataire", "reference",
                "couleur", "taille", "quantite", "motif"]
        preview = result.transfers[[c for c in cols if c in result.transfers.columns]].head(15)
        log.info("Apercu des transferts :\n%s", preview.to_string(index=False))
    print("\n=== Simulation avant/apres ===")
    print(result.simulation_global.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
