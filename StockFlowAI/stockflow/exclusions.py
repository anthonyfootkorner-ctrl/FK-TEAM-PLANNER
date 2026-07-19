"""Références à exclure des réassorts.

Charge une liste de références (fichier déposé par l'utilisateur : xlsx, csv ou
txt) et fournit un masque pour retirer ces références de TOUT le flux :
réassort central (entrepôt → magasins), transferts inter-magasins et Fastmag.

Une référence StockFlow est le ``BarCode V2`` complet (ex. ``0200NZ-010``). On
accepte aussi bien la référence exacte que le *modèle* seul (partie avant le
tiret, ex. ``0200NZ``) : lister le modèle exclut toutes ses couleurs.
"""

from __future__ import annotations

import io
import re
from pathlib import Path
from typing import Iterable, List, Optional

import pandas as pd

# Colonnes plausibles d'un fichier d'exclusions (on prend la premiere trouvee,
# sinon la premiere colonne du fichier).
_REF_COLS = ("reference", "référence", "ref", "réf", "barcode", "barcode v2",
             "code", "code barre", "gencod", "ean", "modele", "modèle", "article")


def norm_token(x) -> str:
    """Normalise un jeton de reference : chaine, sans espaces, majuscules."""
    if x is None:
        return ""
    return str(x).strip().upper()


def _iter_tokens(values: Iterable) -> List[str]:
    out = []
    for v in values:
        if v is None:
            continue
        t = norm_token(v)
        if t and t not in ("NAN", "NONE"):
            out.append(t)
    return out


def _best_delim(line: str) -> Optional[str]:
    """Delimiteur le plus present sur la ligne d'en-tete (ou None si aucun)."""
    counts = {d: line.count(d) for d in (",", ";", "\t")}
    d = max(counts, key=counts.get)
    return d if counts[d] > 0 else None


def _from_df(df: pd.DataFrame) -> List[str]:
    if df is None or df.empty:
        return []
    df.columns = [str(c).strip() for c in df.columns]
    lower = {c.lower(): c for c in df.columns}
    col = next((lower[k] for k in _REF_COLS if k in lower), df.columns[0])
    return _dedupe(_iter_tokens(df[col].tolist()))


def parse_exclusions(src) -> List[str]:
    """Lit un fichier d'exclusions (chemin ou octets/upload) -> liste de refs.

    Formats acceptes : Excel (.xls/.xlsx), CSV/TSV (colonne « reference » sinon
    la premiere), ou texte brut (une ref par ligne, ou separees par , ; espace).
    Renvoie une liste dedupliquee, ordre stable."""
    if src is None:
        return []
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
    if not data:
        return []

    # 1) Excel (detecte par la signature du contenu, pas par l'extension)
    try:
        return _from_df(pd.read_excel(io.BytesIO(data), dtype=str))
    except Exception:
        pass

    # 2) Texte : CSV a en-tete, liste une-par-ligne, ou liste a plat
    text = None
    for enc in ("utf-8-sig", "utf-8", "latin1"):
        try:
            text = data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        return []
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return []
    if len(lines) == 1:
        # liste a plat sur une ligne : separateurs , ; tab ou espaces
        return _dedupe(_iter_tokens(re.split(r"[;,\t\s]+", lines[0].strip())))
    delim = _best_delim(lines[0])
    if delim is None:
        # une reference par ligne
        return _dedupe(_iter_tokens(lines))
    try:
        df = pd.read_csv(io.StringIO(text), dtype=str, sep=delim,
                         keep_default_na=False, na_values=[""])
        return _from_df(df)
    except Exception:
        return _dedupe(_iter_tokens(lines))


def _dedupe(tokens: List[str]) -> List[str]:
    seen, out = set(), []
    for t in tokens:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def to_set(refs: Iterable) -> set:
    """Ensemble normalise a partir d'une liste (ou None)."""
    return {norm_token(x) for x in (refs or []) if norm_token(x) and norm_token(x) != "NAN"}


def excluded_mask(references: pd.Series, refs: Iterable) -> pd.Series:
    """Masque booleen : True la ou la reference doit etre EXCLUE.

    Correspondance sur la reference exacte OU sur le modele (partie avant le
    premier tiret) — lister ``0200NZ`` exclut ``0200NZ-010``, ``0200NZ-020``…"""
    exset = to_set(refs)
    if not exset or references is None:
        return pd.Series(False, index=getattr(references, "index", None))
    ref = references.astype(str).str.strip().str.upper()
    model = ref.str.split("-").str[0]
    return ref.isin(exset) | model.isin(exset)
