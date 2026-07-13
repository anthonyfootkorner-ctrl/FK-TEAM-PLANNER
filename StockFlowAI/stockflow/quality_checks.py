"""Module 1 (suite) - Controle qualite des donnees.

Produit :
* un rapport d'anomalies (liste structuree) ;
* un resume des fichiers charges ;
* un statut bloquant si une colonne essentielle manque.

Les anomalies non bloquantes (references sans vente, magasin sans ville, ...)
sont collectees et retrouvees ensuite dans l'onglet "Cas non traites".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

import pandas as pd

from . import schema


SEVERITE_BLOQUANTE = "BLOQUANTE"
SEVERITE_AVERTISSEMENT = "AVERTISSEMENT"
SEVERITE_INFO = "INFO"


@dataclass
class Anomalie:
    fichier: str
    type: str
    severite: str
    message: str
    nb_lignes: int = 0

    def as_dict(self) -> Dict:
        return {
            "fichier": self.fichier,
            "type": self.type,
            "severite": self.severite,
            "message": self.message,
            "nb_lignes": self.nb_lignes,
        }


@dataclass
class QualityReport:
    anomalies: List[Anomalie] = field(default_factory=list)
    resume: List[Dict] = field(default_factory=list)

    def add(self, anomalie: Anomalie) -> None:
        self.anomalies.append(anomalie)

    @property
    def bloquant(self) -> bool:
        return any(a.severite == SEVERITE_BLOQUANTE for a in self.anomalies)

    def anomalies_df(self) -> pd.DataFrame:
        if not self.anomalies:
            return pd.DataFrame(columns=["fichier", "type", "severite", "message", "nb_lignes"])
        return pd.DataFrame([a.as_dict() for a in self.anomalies])

    def resume_df(self) -> pd.DataFrame:
        return pd.DataFrame(self.resume)


def _check_required(df: pd.DataFrame, required: List[str], fichier: str,
                    report: QualityReport) -> None:
    manquantes = schema.missing_required(df, required)
    if manquantes:
        report.add(Anomalie(
            fichier=fichier, type="colonnes_manquantes",
            severite=SEVERITE_BLOQUANTE,
            message=f"Colonnes essentielles manquantes : {', '.join(manquantes)}",
            nb_lignes=len(df),
        ))


def _check_duplicates(df: pd.DataFrame, keys: List[str], fichier: str,
                      report: QualityReport) -> None:
    keys = [k for k in keys if k in df.columns]
    if not keys or df.empty:
        return
    dup = df.duplicated(subset=keys, keep=False)
    n = int(dup.sum())
    if n:
        report.add(Anomalie(
            fichier=fichier, type="doublons",
            severite=SEVERITE_AVERTISSEMENT,
            message=f"{n} lignes en doublon sur la cle ({', '.join(keys)}) - agregees",
            nb_lignes=n,
        ))


def _check_negative(df: pd.DataFrame, cols: List[str], fichier: str,
                    report: QualityReport) -> None:
    for c in cols:
        if c in df.columns:
            n = int((df[c] < 0).sum())
            if n:
                report.add(Anomalie(
                    fichier=fichier, type="valeur_negative",
                    severite=SEVERITE_AVERTISSEMENT,
                    message=f"{n} valeurs negatives dans '{c}' (mises a 0)",
                    nb_lignes=n,
                ))


def check_stocks(df: pd.DataFrame, report: QualityReport) -> pd.DataFrame:
    fichier = "stocks"
    _check_required(df, schema.STOCK_REQUIRED, fichier, report)
    if report.bloquant:
        return df
    _check_duplicates(df, schema.LINE_KEYS, fichier, report)
    _check_negative(df, ["stock_physique", "stock_disponible"], fichier, report)
    # magasin sans ville
    if "ville" in df.columns:
        sans_ville = df["ville"].isna() | (df["ville"].astype(str).str.strip().isin(["", "nan", "None"]))
        n = int(sans_ville.sum())
        if n:
            report.add(Anomalie(
                fichier=fichier, type="magasin_sans_ville",
                severite=SEVERITE_AVERTISSEMENT,
                message=f"{n} lignes sans ville (proximite geo ignoree pour ces lignes)",
                nb_lignes=n,
            ))
    # aggregation des doublons + valeurs negatives corrigees
    df = df.copy()
    for c in ["stock_physique", "stock_disponible"]:
        if c in df.columns:
            df[c] = df[c].clip(lower=0)
    df = _aggregate_stocks(df)
    return df


def check_sales(df: pd.DataFrame, report: QualityReport) -> pd.DataFrame:
    fichier = "ventes"
    _check_required(df, schema.SALES_REQUIRED, fichier, report)
    if report.bloquant:
        return df
    _check_duplicates(df, schema.LINE_KEYS, fichier, report)
    _check_negative(df, ["ventes_35j", "ventes_7j"], fichier, report)
    df = df.copy()
    for c in ["ventes_35j", "ventes_7j", "ca_35j", "ca_7j"]:
        if c in df.columns:
            df[c] = df[c].clip(lower=0)
    # coherence : ventes 7j > ventes 35j = incoherent
    if {"ventes_7j", "ventes_35j"}.issubset(df.columns):
        n = int((df["ventes_7j"] > df["ventes_35j"] + 1e-9).sum())
        if n:
            report.add(Anomalie(
                fichier=fichier, type="ventes_incoherentes",
                severite=SEVERITE_AVERTISSEMENT,
                message=f"{n} lignes ou ventes_7j > ventes_35j (donnee suspecte)",
                nb_lignes=n,
            ))
    df = _aggregate_sales(df)
    return df


def check_picking(df: pd.DataFrame, report: QualityReport) -> pd.DataFrame:
    fichier = "picking"
    if df.empty:
        return df
    _check_required(df, schema.PICKING_REQUIRED, fichier, report)
    _check_negative(df, ["quantite_prevue"], fichier, report)
    return df


def check_stores(df: pd.DataFrame, report: QualityReport) -> pd.DataFrame:
    fichier = "magasins"
    if df.empty:
        return df
    _check_required(df, schema.STORE_REQUIRED, fichier, report)
    if "code_magasin" in df.columns:
        _check_duplicates(df, ["code_magasin"], fichier, report)
    return df


def check_history(df: pd.DataFrame, report: QualityReport) -> pd.DataFrame:
    if df.empty:
        return df
    _check_required(df, schema.HISTORY_REQUIRED, "historique", report)
    return df


def _aggregate_stocks(df: pd.DataFrame) -> pd.DataFrame:
    keys = [k for k in schema.LINE_KEYS if k in df.columns]
    if not keys:
        return df
    num_cols = [c for c in ["stock_physique", "stock_disponible"] if c in df.columns]
    agg = {c: "sum" for c in num_cols}
    # on garde la premiere valeur pour les colonnes descriptives
    first_cols = [c for c in df.columns if c not in keys + num_cols]
    for c in first_cols:
        agg[c] = "first"
    return df.groupby(keys, as_index=False, dropna=False).agg(agg)


def _aggregate_sales(df: pd.DataFrame) -> pd.DataFrame:
    keys = [k for k in schema.LINE_KEYS if k in df.columns]
    if not keys:
        return df
    num_cols = [c for c in ["ventes_35j", "ventes_7j", "ca_35j", "ca_7j"] if c in df.columns]
    agg = {c: "sum" for c in num_cols}
    if "date_derniere_vente" in df.columns:
        agg["date_derniere_vente"] = "max"
    other = [c for c in df.columns if c not in keys + list(agg.keys())]
    for c in other:
        agg[c] = "first"
    return df.groupby(keys, as_index=False, dropna=False).agg(agg)


def build_summary(datasets: Dict[str, pd.DataFrame], report: QualityReport) -> None:
    """Renseigne le resume des fichiers charges."""
    for name, df in datasets.items():
        report.resume.append({
            "fichier": name,
            "nb_lignes": 0 if df is None else len(df),
            "nb_colonnes": 0 if df is None else df.shape[1],
            "colonnes": "" if df is None else ", ".join(map(str, df.columns[:25])),
        })
