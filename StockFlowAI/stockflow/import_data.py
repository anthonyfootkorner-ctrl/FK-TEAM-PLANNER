"""Module 1 - Import et standardisation des donnees.

Lit les fichiers Excel (stocks, ventes, picking, magasins, historique),
standardise les colonnes via :mod:`stockflow.schema`, normalise les types
(dates, numeriques, booleens) et renvoie des DataFrames propres.

Le controle qualite bloquant est delegue a :mod:`stockflow.quality_checks`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, List

import numpy as np
import pandas as pd

from . import schema


TRUE_TOKENS = {"1", "true", "vrai", "oui", "yes", "o", "y", "x", "web", "picking"}
FALSE_TOKENS = {"0", "false", "faux", "non", "no", "n", "", "nan", "none"}


# ---------------------------------------------------------------------------
# Lecture bas niveau
# ---------------------------------------------------------------------------
def read_excel_files(paths: Iterable[str | Path]) -> pd.DataFrame:
    """Lit un ou plusieurs fichiers Excel/CSV et les concatene.

    Accepte un dossier (tous les .xlsx/.xls/.csv sont lus) ou une liste de
    fichiers. Renvoie un DataFrame brut (colonnes non mappees).
    """
    frames: List[pd.DataFrame] = []
    for p in _expand_paths(paths):
        frames.append(_read_one(p))
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True, sort=False)


def _expand_paths(paths: Iterable[str | Path]) -> List[Path]:
    result: List[Path] = []
    if isinstance(paths, (str, Path)):
        paths = [paths]
    for p in paths:
        p = Path(p)
        if p.is_dir():
            for ext in ("*.xlsx", "*.xls", "*.csv"):
                result.extend(sorted(p.glob(ext)))
        elif p.exists():
            result.append(p)
    return result


def _read_one(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".csv":
        df = pd.read_csv(path, sep=None, engine="python")
    else:
        df = pd.read_excel(path)
    df["_source_fichier"] = path.name
    return df


# ---------------------------------------------------------------------------
# Normalisation de types
# ---------------------------------------------------------------------------
def to_number(series: pd.Series, default: float = 0.0) -> pd.Series:
    """Convertit en numerique (gere virgules decimales et espaces)."""
    if series.dtype.kind in "if":
        return series.fillna(default)
    s = (
        series.astype(str)
        .str.replace(" ", "", regex=False)  # espace insecable fine
        .str.replace(" ", "", regex=False)
        .str.replace(",", ".", regex=False)
    )
    out = pd.to_numeric(s, errors="coerce")
    return out.fillna(default)


def to_bool(series: pd.Series) -> pd.Series:
    def _one(v):
        if isinstance(v, bool):
            return v
        if pd.isna(v):
            return False
        s = str(v).strip().lower()
        if s in TRUE_TOKENS:
            return True
        if s in FALSE_TOKENS:
            return False
        # nombre non nul => vrai
        try:
            return float(s) != 0
        except ValueError:
            return False
    return series.map(_one)


def to_date(series: pd.Series) -> pd.Series:
    # tente d'abord un parsing ISO (silencieux), puis un fallback jour-en-tete
    out = pd.to_datetime(series, errors="coerce", format="mixed", dayfirst=False)
    manquants = out.isna() & series.notna()
    if manquants.any():
        fallback = pd.to_datetime(series[manquants], errors="coerce", dayfirst=True)
        out.loc[manquants] = fallback
    return out


def _clean_key(series: pd.Series) -> pd.Series:
    """Nettoie une cle (reference, magasin, ...) : trim, str, majuscule pour ref."""
    return series.astype(str).str.strip()


# ---------------------------------------------------------------------------
# Loaders specifiques par fichier
# ---------------------------------------------------------------------------
def _ensure_store_col(df: pd.DataFrame) -> pd.DataFrame:
    """Les fichiers lignes utilisent 'magasin' ; on tolere 'code_magasin'."""
    if "magasin" not in df.columns and "code_magasin" in df.columns:
        df = df.rename(columns={"code_magasin": "magasin"})
    return df


def load_stocks(paths: Iterable[str | Path]) -> pd.DataFrame:
    df = _ensure_store_col(schema.map_columns(read_excel_files(paths)))
    if df.empty:
        return df
    for k in ["magasin", "reference", "couleur", "taille"]:
        if k in df:
            df[k] = _clean_key(df[k])
    if "taille" in df:
        df["taille"] = df["taille"].str.upper()
    for c in ["ville", "categorie", "genre", "marque", "statut_reference"]:
        if c in df:
            df[c] = df[c].astype(str).str.strip()
    df["stock_physique"] = to_number(df.get("stock_physique", 0))
    if "stock_disponible" in df:
        df["stock_disponible"] = to_number(df["stock_disponible"])
    else:
        df["stock_disponible"] = df["stock_physique"]
    for c in ["prix_vente", "prix_achat"]:
        if c in df:
            df[c] = to_number(df[c])
    for c in ["date_premiere_reception", "date_derniere_reception"]:
        if c in df:
            df[c] = to_date(df[c])
    df["indic_web"] = to_bool(df["indic_web"]) if "indic_web" in df else False
    df["indic_picking"] = to_bool(df["indic_picking"]) if "indic_picking" in df else False
    return df


def load_sales(paths: Iterable[str | Path]) -> pd.DataFrame:
    df = _ensure_store_col(schema.map_columns(read_excel_files(paths)))
    if df.empty:
        return df
    for k in ["magasin", "reference", "couleur", "taille"]:
        if k in df:
            df[k] = _clean_key(df[k])
    if "taille" in df:
        df["taille"] = df["taille"].str.upper()
    for c in ["ventes_35j", "ventes_7j", "ca_35j", "ca_7j"]:
        if c in df:
            df[c] = to_number(df[c])
        else:
            df[c] = 0.0
    if "date_derniere_vente" in df:
        df["date_derniere_vente"] = to_date(df["date_derniere_vente"])
    return df


def load_picking(paths: Iterable[str | Path]) -> pd.DataFrame:
    df = _ensure_store_col(schema.map_columns(read_excel_files(paths)))
    if df.empty:
        return df
    for k in ["magasin", "reference", "couleur", "taille"]:
        if k in df:
            df[k] = _clean_key(df[k])
    if "taille" in df:
        df["taille"] = df["taille"].str.upper()
    df["quantite_prevue"] = to_number(df.get("quantite_prevue", 0))
    for c in ["date_preparation", "date_reception_prevue"]:
        if c in df:
            df[c] = to_date(df[c])
    if "statut_reassort" in df:
        df["statut_reassort"] = df["statut_reassort"].astype(str).str.strip()
    else:
        df["statut_reassort"] = ""
    return df


def load_stores(paths: Iterable[str | Path]) -> pd.DataFrame:
    df = schema.map_columns(read_excel_files(paths))
    if df.empty:
        return df
    if "code_magasin" not in df.columns and "magasin" in df.columns:
        df = df.rename(columns={"magasin": "code_magasin"})
    if "code_magasin" in df:
        df["code_magasin"] = _clean_key(df["code_magasin"])
    for c in ["nom_magasin", "ville", "region", "type_magasin"]:
        if c in df:
            df[c] = df[c].astype(str).str.strip()
    df["flagship"] = to_bool(df["flagship"]) if "flagship" in df else False
    if "actif" in df:
        df["actif"] = to_bool(df["actif"])
    else:
        df["actif"] = True
    df["priorite"] = to_number(df.get("priorite", 0)) if "priorite" in df else 0.0
    if "capacite" in df:
        df["capacite"] = to_number(df["capacite"])
    return df


def load_history(paths: Iterable[str | Path]) -> pd.DataFrame:
    df = schema.map_columns(read_excel_files(paths))
    if df.empty:
        return df
    for k in ["expediteur", "destinataire", "reference", "couleur", "taille"]:
        if k in df:
            df[k] = _clean_key(df[k])
    if "taille" in df:
        df["taille"] = df["taille"].str.upper()
    if "quantite" in df:
        df["quantite"] = to_number(df["quantite"])
    for c in ["date_transfert", "date_reception"]:
        if c in df:
            df[c] = to_date(df[c])
    return df
