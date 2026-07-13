"""Module 9 - Scoring des transferts.

Chaque transfert candidat recoit une note sur 100. Le score combine des
composantes normalisees (0-1) ponderees par ``poids_scoring`` :

* gain de couverture du receveur ;
* reduction de la couverture excessive du donneur ;
* amelioration de grille et presence de tailles coeur ;
* potentiel de vente et tendance 7 jours ;
* risque de rupture et priorite Top 30 ;
* statut flagship (bonus borne) ;
* distance (a potentiel egal, le plus proche gagne) ;
* regroupement logistique (destination deja ouverte) ;
* penalite d'historique (anti transfert en boucle / croise).

Le moteur produit egalement un motif lisible pour chaque recommandation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from .parameters import Parameters, classer_score


@dataclass
class Candidate:
    expediteur: str
    destinataire: str
    reference: str
    couleur: str
    taille: str
    qte: float
    # donneur
    is_web_don: bool
    cov_don_avant: float
    cov_don_apres: float
    daily_don: float
    grid_don_avant: str
    grid_don_apres: str
    grid_don_valide_apres: bool
    # receveur
    cov_rec_avant: float
    cov_rec_apres: float
    daily_rec: float
    tendance_rec: str
    grid_rec_coeur_avant: int
    grid_rec_coeur_apres: int
    grid_rec_avant: str
    grid_rec_apres: str
    type_besoin: str
    # contexte
    distance_km: float
    flagship_rec: bool
    criticite_rec: float
    dans_top30: bool
    destination_deja_ouverte: bool
    penalite_historique: float
    # sorties
    stock_don_avant: float = 0.0
    stock_don_apres: float = 0.0
    stock_rec_avant: float = 0.0
    stock_rec_apres: float = 0.0
    besoin_residuel: float = 0.0
    picking_prevu: float = 0.0


class TransferScorer:
    def __init__(self, params: Parameters):
        self.params = params
        self.weights: Dict[str, float] = dict(params.get("poids_scoring", {}))
        self.total_weight = sum(self.weights.values()) or 1.0
        self.cible = float(params.get("couverture_cible_magasin", 30))
        self.dist_max = float(params.get("distance_max_km", 800))
        self.bonus_flagship = float(params.get("bonus_flagship", 5))

    # -- composantes 0-1 -----------------------------------------------------
    def _components(self, c: Candidate) -> Dict[str, float]:
        comp: Dict[str, float] = {}

        # gain de couverture du receveur (borne a la cible)
        gain = max(0.0, c.cov_rec_apres - c.cov_rec_avant)
        comp["gain_couverture_receveur"] = min(1.0, gain / self.cible)

        # reduction du surstock donneur (au-dela de la cible) - utile surtout Web/dormant
        exces_avant = max(0.0, c.cov_don_avant - self.cible)
        exces_apres = max(0.0, c.cov_don_apres - self.cible)
        comp["reduction_surstock_donneur"] = min(1.0, (exces_avant - exces_apres) / self.cible) if exces_avant > 0 else 0.0

        # amelioration de grille (tailles coeur gagnees)
        gain_coeur = max(0, c.grid_rec_coeur_apres - c.grid_rec_coeur_avant)
        comp["amelioration_grille"] = min(1.0, gain_coeur / 2.0)

        # presence de tailles coeur apres (atteinte du minimum)
        comp["tailles_coeur"] = 1.0 if c.grid_rec_coeur_apres >= int(self.params.get("min_tailles_coeur_receveur", 2)) else 0.4 * c.grid_rec_coeur_apres

        # potentiel de vente du receveur (rythme quotidien)
        comp["potentiel_vente"] = min(1.0, c.daily_rec / 2.0)

        # tendance 7j
        comp["tendance_7j"] = {"hausse": 1.0, "stable": 0.5, "baisse": 0.0}.get(c.tendance_rec, 0.5)

        # risque de rupture receveur (couverture avant faible = urgent)
        if c.cov_rec_avant <= 0:
            comp["risque_rupture"] = 1.0
        elif c.cov_rec_avant < 7:
            comp["risque_rupture"] = 0.9
        elif c.cov_rec_avant < 14:
            comp["risque_rupture"] = 0.6
        elif c.cov_rec_avant < self.cible:
            comp["risque_rupture"] = 0.3
        else:
            comp["risque_rupture"] = 0.0

        # priorite Top 30
        comp["priorite_top30"] = 1.0 if c.dans_top30 else 0.0

        # flagship (borne pour eviter le favoritisme)
        comp["flagship"] = 1.0 if c.flagship_rec else 0.0

        # distance (1 = tres proche, 0 = tres loin)
        comp["distance"] = max(0.0, 1.0 - min(1.0, c.distance_km / self.dist_max))

        # regroupement logistique
        comp["regroupement_logistique"] = 1.0 if c.destination_deja_ouverte else 0.0

        # penalite historique (anti-boucle / croise) : composante negative
        comp["historique_penalite"] = -min(1.0, c.penalite_historique)

        return comp

    # -- score final ---------------------------------------------------------
    def score(self, c: Candidate) -> "ScoredTransfer":
        comp = self._components(c)
        raw = 0.0
        for key, w in self.weights.items():
            raw += w * comp.get(key, 0.0)
        score = 100.0 * raw / self.total_weight
        # bonus flagship additif borne
        if c.flagship_rec:
            score += self.bonus_flagship
        score = max(0.0, min(100.0, score))
        return ScoredTransfer(candidate=c, score=round(score, 1),
                              priorite=classer_score(score),
                              composantes=comp, motif=self._motif(c, comp))

    def _motif(self, c: Candidate, comp: Dict[str, float]) -> str:
        raisons: List[str] = []
        if comp["risque_rupture"] >= 0.6:
            raisons.append(f"couvre un risque de rupture ({c.cov_rec_avant:.0f}j)")
        if comp["amelioration_grille"] > 0:
            raisons.append(f"ameliore la grille ({c.grid_rec_avant} -> {c.grid_rec_apres})")
        if c.dans_top30:
            raisons.append("reference du Top 30 magasin")
        if c.tendance_rec == "hausse":
            raisons.append("ventes en acceleration")
        if c.is_web_don:
            raisons.append("puise dans la reserve Web")
        elif comp["reduction_surstock_donneur"] > 0:
            raisons.append("degage un surstock donneur")
        if c.destination_deja_ouverte:
            raisons.append("regroupe sur une destination existante")
        if c.distance_km == 0:
            raisons.append("meme ville")
        if not raisons:
            raisons.append("optimise la couverture reseau")
        return " ; ".join(raisons)


@dataclass
class ScoredTransfer:
    candidate: Candidate
    score: float
    priorite: str
    composantes: Dict[str, float]
    motif: str
