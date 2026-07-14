"""Generateur de jeux de donnees de demonstration.

Aucune donnee reelle n'a ete fournie pour la V1 ; ce module fabrique des
fichiers Excel coherents (stocks, ventes, picking, magasins, historique) pour :
* faire tourner le moteur de bout en bout ;
* alimenter les tests unitaires ;
* servir de reference de format (dictionnaire de donnees vivant).

Les donnees sont deterministes (aucun aleatoire non seed) afin que les
simulations restent reproductibles.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Tuple

import numpy as np
import pandas as pd


VILLES = {
    "PAR": "Paris", "LYO": "Lyon", "MAR": "Marseille",
    "BOR": "Bordeaux", "LIL": "Lille", "WEB": "Entrepot",
}
TAILLES = ["S", "M", "L", "XL"]
COULEURS = ["NOIR", "BLANC"]
REFERENCES = [f"REF{i:03d}" for i in range(1, 13)]


def _seed():
    return np.random.default_rng(42)


def build_stores() -> pd.DataFrame:
    rows = [
        {"code_magasin": "PAR", "nom_magasin": "Paris Rivoli", "ville": "Paris", "region": "IDF", "flagship": True, "type_magasin": "FLAGSHIP", "actif": True, "priorite": 3, "capacite": 5000},
        {"code_magasin": "LYO", "nom_magasin": "Lyon Presqu'ile", "ville": "Lyon", "region": "ARA", "flagship": False, "type_magasin": "STANDARD", "actif": True, "priorite": 1, "capacite": 3000},
        {"code_magasin": "MAR", "nom_magasin": "Marseille Prado", "ville": "Marseille", "region": "PACA", "flagship": False, "type_magasin": "STANDARD", "actif": True, "priorite": 1, "capacite": 3000},
        {"code_magasin": "BOR", "nom_magasin": "Bordeaux Sainte-Cath", "ville": "Bordeaux", "region": "NAQ", "flagship": False, "type_magasin": "STANDARD", "actif": True, "priorite": 1, "capacite": 2500},
        {"code_magasin": "LIL", "nom_magasin": "Lille Grand Place", "ville": "Lille", "region": "HDF", "flagship": True, "type_magasin": "FLAGSHIP", "actif": True, "priorite": 2, "capacite": 3500},
        {"code_magasin": "WEB", "nom_magasin": "Stock Web", "ville": "Entrepot", "region": "WEB", "flagship": False, "type_magasin": "WEB", "actif": True, "priorite": 0, "capacite": 50000},
    ]
    return pd.DataFrame(rows)


def build_all() -> Dict[str, pd.DataFrame]:
    rng = _seed()
    stores = build_stores()
    stock_rows, sales_rows = [], []

    for code in stores["code_magasin"]:
        is_web = code == "WEB"
        for ref in REFERENCES:
            for coul in COULEURS:
                # popularite de la reference (deterministe par index)
                pop = 0.2 + (int(ref[3:]) % 6) * 0.5  # ventes/jour de base
                for taille in TAILLES:
                    # certaines tailles absentes pour creer des grilles incompletes
                    taille_factor = {"S": 0.8, "M": 1.2, "L": 1.0, "XL": 0.5}[taille]
                    if not is_web and rng.random() < 0.18:
                        continue  # taille non implantee
                    base_sales = pop * taille_factor
                    v35 = int(max(0, rng.poisson(base_sales * 35)))
                    v7 = int(max(0, rng.poisson(base_sales * 7 * (1.3 if rng.random() < 0.3 else 0.9))))
                    if is_web:
                        stock = int(rng.integers(20, 120))
                    else:
                        # stock parfois faible (rupture) parfois eleve (surstock)
                        cov_target = rng.choice([3, 10, 25, 45, 80])
                        stock = int(max(0, base_sales * cov_target + rng.integers(-3, 4)))
                    pv = 20 + (int(ref[3:]) % 5) * 10
                    stock_rows.append({
                        "magasin": code, "ville": VILLES[code], "reference": ref,
                        "couleur": coul, "taille": taille,
                        "stock_physique": stock, "stock_disponible": stock,
                        "categorie": "TEXTILE_HOMME", "genre": "HOMME", "marque": "FK",
                        "prix_vente": pv, "prix_achat": pv * 0.45,
                        "date_premiere_reception": "2025-09-01",
                        "date_derniere_reception": "2026-06-15",
                        "statut_reference": "ACTIF",
                        "indic_web": is_web, "indic_picking": False,
                    })
                    if not is_web or v35 > 0:
                        sales_rows.append({
                            "magasin": code, "reference": ref, "couleur": coul,
                            "taille": taille, "ventes_35j": v35, "ventes_7j": v7,
                            "ca_35j": v35 * pv, "ca_7j": v7 * pv,
                            "date_derniere_vente": "2026-07-10",
                        })

    stocks = pd.DataFrame(stock_rows)
    sales = pd.DataFrame(sales_rows)

    # picking : quelques reassorts deja programmes (dont un qui couvre un besoin)
    picking = pd.DataFrame([
        {"magasin": "LYO", "reference": "REF002", "couleur": "NOIR", "taille": "M",
         "quantite_prevue": 15, "date_preparation": "2026-07-11",
         "date_reception_prevue": "2026-07-15", "statut_reassort": "PREPARE",
         "id_mouvement": "PK001"},
        {"magasin": "MAR", "reference": "REF004", "couleur": "BLANC", "taille": "L",
         "quantite_prevue": 8, "date_preparation": "2026-07-12",
         "date_reception_prevue": "2026-07-16", "statut_reassort": "EN_COURS",
         "id_mouvement": "PK002"},
        {"magasin": "BOR", "reference": "REF001", "couleur": "NOIR", "taille": "S",
         "quantite_prevue": 5, "date_preparation": "2026-07-01",
         "date_reception_prevue": "2026-07-05", "statut_reassort": "RECEPTIONNE",
         "id_mouvement": "PK003"},
    ])

    history = pd.DataFrame([
        {"expediteur": "PAR", "destinataire": "LIL", "reference": "REF003",
         "couleur": "NOIR", "taille": "L", "quantite": 6, "date_transfert": "2026-06-20",
         "statut": "RECU", "date_reception": "2026-06-23", "resultat_vente": 4},
    ])

    return {"stocks": stocks, "ventes": sales, "picking": picking,
            "magasins": stores, "historique": history}


def write_all(base_dir: str | Path) -> Dict[str, Path]:
    base_dir = Path(base_dir)
    data = build_all()
    paths: Dict[str, Path] = {}
    mapping = {
        "stocks": base_dir / "stocks" / "stocks_demo.xlsx",
        "ventes": base_dir / "ventes" / "ventes_demo.xlsx",
        "picking": base_dir / "picking" / "picking_demo.xlsx",
        "magasins": base_dir / "magasins" / "magasins_demo.xlsx",
        "historique": base_dir / "historique" / "historique_demo.xlsx",
    }
    for key, path in mapping.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        data[key].to_excel(path, index=False)
        paths[key] = path
    return paths
