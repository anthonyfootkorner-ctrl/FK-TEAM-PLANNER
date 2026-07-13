"""Gestion des parametres du moteur.

Regle d'or du brief : *aucune regle metier ne doit etre codee en dur*.
Toutes les valeurs de reference sont regroupees ici sous forme de valeurs par
defaut, et peuvent etre surchargees par un fichier ``config/parametres.xlsx``.

Le fichier de parametres est optionnel : en son absence le moteur fonctionne
avec les valeurs par defaut ci-dessous, ce qui garantit qu'une simulation reste
reproductible et versionnable (on conserve la copie des parametres utilises dans
le journal et l'export).
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd


# ---------------------------------------------------------------------------
# Valeurs par defaut (documentees dans le brief, section 2 et 3.6)
# ---------------------------------------------------------------------------
DEFAULTS: Dict[str, Any] = {
    # Couvertures (en jours)
    "couverture_cible_magasin": 30,     # cible receveur apres reassort
    "couverture_min_expediteur": 20,    # a conserver apres transfert
    "couverture_min_web": 30,           # reserve strategique protegee
    # Logistique
    "nb_max_destinations": 4,           # destinations / expediteur / semaine
    # Periodes d'analyse (jours)
    "periode_ventes": 35,
    "periode_tendance": 7,
    # Detection de tendance : variation relative du rythme 7j vs 35j
    "seuil_tendance_hausse": 0.15,      # +15% => acceleration
    "seuil_tendance_baisse": -0.15,     # -15% => ralentissement
    # Stock dormant : jours sans vente avec du stock => dormant
    "seuil_dormant_jours": 60,
    "couverture_dormant": 999,          # convention brief (module 3)
    # Grilles de tailles
    "tailles_coeur": {
        # categorie / famille de taille -> liste de tailles coeur (module 2.6)
        "TEXTILE_HOMME": ["S", "M", "L"],
        "TEXTILE_FEMME": ["36", "38", "40"],
        # familles issues de la standardisation des tailles reelles (sizes.py)
        "LETTRE": ["S", "M", "L"],
        "CHAUSSURE": ["42", "43", "44"],
        "ENFANT": [],
        "AUTRE": [],
        "DEFAUT": ["S", "M", "L"],
    },
    "min_tailles_coeur_receveur": 2,    # au moins 2 tailles coeur apres reassort
    # Scoring (poids, section module 9). La somme est normalisee au calcul.
    "poids_scoring": {
        "gain_couverture_receveur": 20,
        "reduction_surstock_donneur": 10,
        "amelioration_grille": 15,
        "tailles_coeur": 12,
        "potentiel_vente": 12,
        "tendance_7j": 8,
        "risque_rupture": 15,
        "priorite_top30": 10,
        "flagship": 5,
        "distance": 8,
        "regroupement_logistique": 6,
        "historique_penalite": 5,
    },
    # Indice de criticite magasin (module 8)
    "poids_criticite": {
        "risque_rupture_top30": 0.40,
        "potentiel_commercial": 0.25,
        "flagship": 0.15,
        "couverture_moyenne": 0.10,
        "tendance": 0.10,
    },
    # Bonus flagship (points ajoutes au score, borne pour eviter le favoritisme)
    "bonus_flagship": 5,
    # Distance
    "poids_distance": 8,
    "distance_defaut_km": 150,          # 2 villes differentes sans matrice fournie
    "distance_max_km": 800,             # normalisation du score distance
    # Delai de protection apres reception (jours) : anti-chaine / anti-boucle
    "delai_protection_jours": 21,
    # Implantation : score minimal pour proposer une nouvelle implantation
    "seuil_proposition_implantation": 70,
    # Seuils de selection des transferts (module 9)
    "seuil_score_minimum": 60,          # en dessous : non retenu
    # Exclusions
    "exclusions_marque": [],
    "exclusions_saison": [],
    "exclusions_reference": [],
    # Magasins inactifs (codes) - complete par le fichier magasins
    "magasins_inactifs": [],
    # Top N references par magasin pour la criticite
    "top_n_references": 30,
    # Anti-boucle du moteur
    "max_iterations": 5000,
    # Quantite minimale d'un transfert (le brief : pas de minimum obligatoire)
    "quantite_min_transfert": 1,
}

# Bornes de classement des scores (module 9)
CLASSEMENT_SCORE = [
    (90, "Prioritaire"),
    (80, "Fortement recommande"),
    (70, "Recommande"),
    (60, "A valider"),
    (0, "Non retenu"),
]


def classer_score(score: float) -> str:
    """Retourne le libelle de priorite pour un score sur 100."""
    for seuil, libelle in CLASSEMENT_SCORE:
        if score >= seuil:
            return libelle
    return "Non retenu"


@dataclass
class Parameters:
    """Conteneur de parametres, initialise avec :data:`DEFAULTS`."""

    values: Dict[str, Any] = field(default_factory=lambda: copy.deepcopy(DEFAULTS))
    source: str = "defaults"

    # -- acces ----------------------------------------------------------------
    def get(self, key: str, default: Any = None) -> Any:
        return self.values.get(key, default)

    def __getitem__(self, key: str) -> Any:
        return self.values[key]

    def set(self, key: str, value: Any) -> None:
        self.values[key] = value

    # -- tailles coeur --------------------------------------------------------
    def tailles_coeur_for(self, categorie: str | None) -> List[str]:
        table = self.values.get("tailles_coeur", {})
        if categorie is not None:
            cat = str(categorie).strip().upper().replace(" ", "_")
            if cat in table:
                return list(table[cat])
        return list(table.get("DEFAUT", ["S", "M", "L"]))

    # -- chargement / sauvegarde ---------------------------------------------
    @classmethod
    def load(cls, path: str | Path | None = None) -> "Parameters":
        """Charge les parametres depuis un xlsx (si present), sinon defauts.

        Le fichier ``parametres.xlsx`` doit contenir une feuille ``parametres``
        avec deux colonnes : ``cle`` et ``valeur``. Les valeurs peuvent etre
        des scalaires ou du JSON (pour les dictionnaires / listes).
        """
        params = cls()
        if path is None:
            return params
        path = Path(path)
        if not path.exists():
            return params
        try:
            xls = pd.ExcelFile(path)
        except Exception:
            return params

        # Feuille principale cle/valeur
        if "parametres" in xls.sheet_names:
            df = xls.parse("parametres")
            df.columns = [str(c).strip().lower() for c in df.columns]
            if {"cle", "valeur"}.issubset(df.columns):
                for _, row in df.iterrows():
                    key = str(row["cle"]).strip()
                    if not key or key.lower() == "nan":
                        continue
                    params.values[key] = _coerce(row["valeur"])

        # Feuille dediee aux tailles coeur (config/tailles_coeur.xlsx style)
        if "tailles_coeur" in xls.sheet_names:
            df = xls.parse("tailles_coeur")
            params.values["tailles_coeur"] = _parse_tailles_coeur(df)

        params.source = str(path)
        return params

    def load_tailles_coeur(self, path: str | Path | None) -> "Parameters":
        """Fusionne un fichier ``tailles_coeur.xlsx`` externe."""
        if path is None:
            return self
        path = Path(path)
        if not path.exists():
            return self
        try:
            df = pd.read_excel(path)
        except Exception:
            return self
        self.values["tailles_coeur"] = _parse_tailles_coeur(df)
        return self

    def to_dataframe(self) -> pd.DataFrame:
        """Serialise les parametres pour l'onglet Parametres de l'export."""
        rows = []
        for key, value in self.values.items():
            if isinstance(value, (dict, list)):
                value = json.dumps(value, ensure_ascii=False)
            rows.append({"cle": key, "valeur": value})
        return pd.DataFrame(rows)

    def snapshot(self) -> Dict[str, Any]:
        """Copie profonde pour journalisation / reproductibilite."""
        return copy.deepcopy(self.values)

    def save_template(self, path: str | Path) -> Path:
        """Ecrit un fichier de parametres modele (config/parametres.xlsx)."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            self.to_dataframe().to_excel(writer, sheet_name="parametres", index=False)
            # feuille tailles coeur explicite
            rows = []
            for cat, tailles in self.values.get("tailles_coeur", {}).items():
                for t in tailles:
                    rows.append({"categorie": cat, "taille_coeur": t})
            pd.DataFrame(rows).to_excel(writer, sheet_name="tailles_coeur", index=False)
        return path


def _coerce(value: Any) -> Any:
    """Convertit une valeur de cellule (json, nombre, bool, str)."""
    if isinstance(value, (int, float, bool)):
        # pandas peut renvoyer des floats pour des entiers
        if isinstance(value, float) and value.is_integer():
            return int(value)
        return value
    if value is None:
        return None
    s = str(value).strip()
    if s == "" or s.lower() == "nan":
        return None
    # JSON (dict/list/bool)
    if s[0] in "[{" or s.lower() in ("true", "false"):
        try:
            return json.loads(s)
        except Exception:
            pass
    # nombre
    try:
        if "." in s:
            return float(s)
        return int(s)
    except ValueError:
        return s


def _parse_tailles_coeur(df: pd.DataFrame) -> Dict[str, List[str]]:
    df = df.copy()
    df.columns = [str(c).strip().lower() for c in df.columns]
    result: Dict[str, List[str]] = {}
    if {"categorie", "taille_coeur"}.issubset(df.columns):
        for _, row in df.iterrows():
            cat = str(row["categorie"]).strip().upper().replace(" ", "_")
            taille = str(row["taille_coeur"]).strip()
            if not cat or not taille or cat == "NAN" or taille == "nan":
                continue
            result.setdefault(cat, []).append(taille)
    if "DEFAUT" not in result:
        result["DEFAUT"] = ["S", "M", "L"]
    return result
