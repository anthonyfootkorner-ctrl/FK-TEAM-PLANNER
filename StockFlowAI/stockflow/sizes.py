"""Standardisation des tailles reelles (exports Fastmag).

Les exports melangent plusieurs systemes de tailles (728 variantes observees) :
* lettres adultes : XS, S, M, L, XL, XXL, TU... ;
* chaussures EU : 36, 42, 44.5, 40.5... ;
* enfant : "2/3 ANS", "24M", "10/12 ANS"... ;
* divers / bruit : "-", "0", "S/M".

On normalise chaque taille en un couple (taille_normalisee, famille_taille).
La famille pilote les "tailles coeur" : la regle S/M/L ne s'applique qu'aux
lettres adultes ; pour les autres familles la regle de grille est neutre
(non bloquante), ce qui evite de bloquer a tort chaussures et enfant.
"""

from __future__ import annotations

import re
from typing import Tuple

# familles
LETTRE = "LETTRE"
CHAUSSURE = "CHAUSSURE"
ENFANT = "ENFANT"
AUTRE = "AUTRE"

_LETTERS = {
    "XXS": "XXS", "XS": "XS", "S": "S", "M": "M", "L": "L", "XL": "XL",
    "XXL": "XXL", "XXXL": "XXXL", "2XL": "XXL", "3XL": "XXXL", "1XL": "XL",
    "TU": "TU", "T.U": "TU", "TU.": "TU", "U": "TU", "UNI": "TU", "UNIQUE": "TU",
}

_RE_KID = re.compile(r"(ANS|MOIS|\bMOIS\b)", re.I)
_RE_KID2 = re.compile(r"^\d{1,2}\s*[-/]\s*\d{1,2}\s*A?$")   # 10/12, 6-8A
_RE_KID3 = re.compile(r"^\d{1,2}\s*A$", re.I)               # 6A, 10A
_RE_KID_MONTH = re.compile(r"^\d{1,2}\s*M$", re.I)          # 24M, 18M
_RE_SHOE = re.compile(r"^\d{2}([.,]\d)?$")                   # 42, 42.5
_RE_SHOE_FRAC = re.compile(r"^\d{2}\s*\d/\d$")               # 40 2/3, 36 2/3


def normalize_size(raw) -> Tuple[str, str]:
    """Retourne (taille_normalisee, famille)."""
    if raw is None:
        return "?", AUTRE
    s = str(raw).strip().upper()
    s = re.sub(r"\s+", " ", s).strip()
    if s in ("", "-", "NAN", "NONE", "0", "?"):
        return "?", AUTRE

    # lettres adultes
    key = s.replace(" ", "").replace(".", "")
    if key in _LETTERS:
        return _LETTERS[key], LETTRE
    # combinaisons de lettres type S/M, L/XL -> famille lettre, garde tel quel
    if re.fullmatch(r"(X{0,3}[SLM]L?|TU)(/(X{0,3}[SLM]L?))+", key):
        return key, LETTRE

    # enfant
    if _RE_KID.search(s) or _RE_KID2.match(s) or _RE_KID3.match(s) or _RE_KID_MONTH.match(s):
        return s, ENFANT

    # chaussures EU
    if _RE_SHOE.match(s):
        return s.replace(",", "."), CHAUSSURE
    if _RE_SHOE_FRAC.match(s):
        return s, CHAUSSURE

    return s, AUTRE


# tailles coeur par famille (surcharge possible via parametres.tailles_coeur)
CORE_BY_FAMILY = {
    LETTRE: ["S", "M", "L"],
    CHAUSSURE: ["42", "43", "44"],   # cœur de gamme homme EU
    ENFANT: [],                       # regle de grille neutre
    AUTRE: [],
}
