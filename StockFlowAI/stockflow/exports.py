"""Module exports - Generation de l'export Excel (7 onglets).

1. Transferts recommandes
2. Synthese par flux
3. Simulation avant/apres
4. Propositions d'implantation
5. Cas non traites
6. Parametres
7. Journal d'execution
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .parameters import Parameters


# libelles finaux (colonnes) pour l'onglet transferts
TRANSFER_LABELS = {
    "priorite": "Priorite",
    "score": "Score",
    "expediteur": "Expediteur",
    "destinataire": "Destinataire",
    "reference": "Reference",
    "couleur": "Couleur",
    "taille": "Taille",
    "quantite": "Quantite",
    "stock_exp_avant": "Stock expediteur avant",
    "stock_exp_apres": "Stock expediteur apres",
    "cov_exp_avant": "Couv. expediteur avant",
    "cov_exp_apres": "Couv. expediteur apres",
    "stock_dest_avant": "Stock destinataire avant",
    "stock_dest_apres": "Stock destinataire apres",
    "cov_dest_avant": "Couv. destinataire avant",
    "cov_dest_apres": "Couv. destinataire apres",
    "grille_avant": "Grille avant",
    "grille_apres": "Grille apres",
    "picking_prevu": "Reassort Picking prevu",
    "besoin_residuel": "Besoin residuel",
    "motif": "Motif du transfert",
    "distance_km": "Distance estimee (km)",
    "destination_num": "Destination n0",
}


def build_flux_summary(transfers: pd.DataFrame, base: pd.DataFrame,
                       params: Parameters) -> pd.DataFrame:
    """Onglet 2 - synthese par flux (expediteur -> destinataire)."""
    cols = ["expediteur", "destinataire", "nb_references", "nb_tailles", "nb_pieces",
            "valeur_stock", "score_moyen", "priorite", "nb_colis_estime"]
    if transfers is None or transfers.empty:
        return pd.DataFrame(columns=cols)

    prix = base.drop_duplicates(["reference", "couleur", "taille"]).set_index(
        ["reference", "couleur", "taille"])["prix_vente"] if "prix_vente" in base else None

    def _valeur(group: pd.DataFrame) -> float:
        total = 0.0
        for t in group.itertuples(index=False):
            pv = 0.0
            if prix is not None:
                try:
                    pv = float(prix.loc[(t.reference, t.couleur, t.taille)])
                except Exception:
                    pv = 0.0
            total += t.quantite * pv
        return total

    pieces_par_colis = 30  # estimation logistique simple
    rows = []
    for (exp, dest), g in transfers.groupby(["expediteur", "destinataire"]):
        pieces = float(g["quantite"].sum())
        score_moy = round(float(g["score"].mean()), 1)
        rows.append({
            "expediteur": exp,
            "destinataire": dest,
            "nb_references": int(g["reference"].nunique()),
            "nb_tailles": int(len(g)),
            "nb_pieces": pieces,
            "valeur_stock": round(_valeur(g), 0),
            "score_moyen": score_moy,
            "priorite": _priorite_from_score(score_moy, params),
            "nb_colis_estime": max(1, math.ceil(pieces / pieces_par_colis)),
        })
    return pd.DataFrame(rows).sort_values("score_moyen", ascending=False).reset_index(drop=True)


def _priorite_from_score(score: float, params: Parameters) -> str:
    from .parameters import classer_score
    return classer_score(score)


def build_cas_non_traites(optimizer_result, needs: pd.DataFrame,
                          quality_report, base: pd.DataFrame,
                          web_codes) -> pd.DataFrame:
    """Onglet 5 - cas non traites (blocages, besoins sans donneur, anomalies)."""
    rows: List[Dict] = []

    # blocages du moteur
    for b in optimizer_result.blocked:
        rows.append({
            "categorie": "Transfert bloque",
            "magasin": b.get("magasin", ""),
            "reference": b.get("reference", ""),
            "couleur": b.get("couleur", ""),
            "taille": b.get("taille", ""),
            "detail": b.get("motif_blocage", ""),
        })

    # besoins non couverts (qte_restante > 0)
    if needs is not None and not needs.empty and "qte_restante" in needs:
        reste = needs[needs["qte_restante"] > 0]
        for r in reste.itertuples(index=False):
            rows.append({
                "categorie": "Besoin non couvert",
                "magasin": str(r.magasin),
                "reference": str(r.reference),
                "couleur": str(r.couleur),
                "taille": str(r.taille),
                "detail": f"Besoin residuel {getattr(r, 'qte_restante', 0):.0f} ({getattr(r, 'type_besoin', '')})",
            })

    # references sans vente (dormant / stock sans ventes)
    if base is not None and not base.empty:
        sans_vente = base[(base["moyenne_quotidienne"] <= 0) & (base["stock_actuel"] > 0)]
        agg = sans_vente.groupby(["magasin", "reference"], as_index=False)["stock_actuel"].sum()
        for r in agg.head(500).itertuples(index=False):
            rows.append({
                "categorie": "Reference sans vente (dormant)",
                "magasin": str(r.magasin),
                "reference": str(r.reference),
                "couleur": "",
                "taille": "",
                "detail": f"{r.stock_actuel:.0f} pieces sans vente sur la periode",
            })
        # magasins sans ville
        if "ville" in base:
            sans_ville = base[base["ville"].astype(str).str.strip().isin(["", "nan", "None"])]
            for mag in sorted(sans_ville["magasin"].astype(str).unique()):
                rows.append({"categorie": "Magasin sans ville", "magasin": mag,
                             "reference": "", "couleur": "", "taille": "",
                             "detail": "Proximite geo non exploitable"})

    # anomalies qualite non bloquantes
    if quality_report is not None:
        for a in quality_report.anomalies:
            rows.append({
                "categorie": f"Anomalie donnee ({a.severite})",
                "magasin": "",
                "reference": "",
                "couleur": "",
                "taille": "",
                "detail": f"[{a.fichier}] {a.message}",
            })

    cols = ["categorie", "magasin", "reference", "couleur", "taille", "detail"]
    if not rows:
        return pd.DataFrame(columns=cols)
    return pd.DataFrame(rows)[cols]


def build_journal(journal: Dict) -> pd.DataFrame:
    rows = [{"cle": k, "valeur": v} for k, v in journal.items()]
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Ecriture Excel avec mise en forme
# ---------------------------------------------------------------------------
HEADER_FILL = PatternFill("solid", fgColor="1a1d29")
HEADER_FONT = Font(color="FFFFFF", bold=True, size=11)
PRIO_FILLS = {
    "Prioritaire": PatternFill("solid", fgColor="C6EFCE"),
    "Fortement recommande": PatternFill("solid", fgColor="D9EAD3"),
    "Recommande": PatternFill("solid", fgColor="FFF2CC"),
    "A valider": PatternFill("solid", fgColor="FCE5CD"),
}


def _write_sheet(writer, sheet_name: str, df: pd.DataFrame, prio_col: str | None = None):
    df.to_excel(writer, sheet_name=sheet_name, index=False)
    ws = writer.sheets[sheet_name]
    for col_idx, col in enumerate(df.columns, start=1):
        cell = ws.cell(row=1, column=col_idx)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        # largeur auto approx
        maxlen = max([len(str(col))] + [len(str(v)) for v in df[col].astype(str).head(200)])
        ws.column_dimensions[get_column_letter(col_idx)].width = min(45, max(10, maxlen + 2))
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    # coloration priorite
    if prio_col and prio_col in df.columns:
        pcol = list(df.columns).index(prio_col) + 1
        for r in range(len(df)):
            val = df.iloc[r][prio_col]
            fill = PRIO_FILLS.get(str(val))
            if fill:
                ws.cell(row=r + 2, column=pcol).fill = fill


def export_excel(path: str | Path, *, transfers: pd.DataFrame, flux: pd.DataFrame,
                 simulation_global: pd.DataFrame, simulation_stores: pd.DataFrame,
                 implantations: pd.DataFrame, cas_non_traites: pd.DataFrame,
                 parametres: pd.DataFrame, journal: pd.DataFrame,
                 top_references: pd.DataFrame | None = None,
                 criticite: pd.DataFrame | None = None) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # onglet transferts : renommage lisible
    t = transfers.copy() if transfers is not None else pd.DataFrame()
    if not t.empty:
        ordered = [c for c in TRANSFER_LABELS if c in t.columns]
        extra = [c for c in t.columns if c not in TRANSFER_LABELS]
        t = t[ordered + extra].rename(columns=TRANSFER_LABELS)

    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        _write_sheet(writer, "1-Transferts", t if not t.empty else pd.DataFrame({"Info": ["Aucun transfert retenu"]}),
                     prio_col="Priorite")
        _write_sheet(writer, "2-Synthese flux", flux if not flux.empty else pd.DataFrame({"Info": ["Aucun flux"]}),
                     prio_col="priorite")
        _write_sheet(writer, "3-Simulation", simulation_global)
        if simulation_stores is not None and not simulation_stores.empty:
            _write_sheet(writer, "3b-Simulation magasins", simulation_stores)
        _write_sheet(writer, "4-Implantations",
                     implantations if not implantations.empty else pd.DataFrame({"Info": ["Aucune proposition"]}))
        _write_sheet(writer, "5-Cas non traites",
                     cas_non_traites if not cas_non_traites.empty else pd.DataFrame({"Info": ["Aucun cas"]}))
        _write_sheet(writer, "6-Parametres", parametres)
        _write_sheet(writer, "7-Journal", journal)
        if top_references is not None and not top_references.empty:
            _write_sheet(writer, "8-Top references", top_references)
        if criticite is not None and not criticite.empty:
            _write_sheet(writer, "9-Criticite magasins", criticite)

    return path
