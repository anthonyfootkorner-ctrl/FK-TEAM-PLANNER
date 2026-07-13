"""Module 10 - Moteur d'optimisation iteratif.

Boucle : generer les candidats -> scorer -> selectionner le meilleur ->
mettre a jour stocks / grilles / couvertures / destinations -> recommencer.

Regles anti-erreur appliquees (module 5) :
* anti-double reassort (besoin residuel deja net du Picking) ;
* anti-transfert croise (A->B interdit si B->A deja retenu) ;
* anti-transfert en chaine (delai de protection + lignes recues verrouillees) ;
* anti-casse de grille (donneur et receveur) ;
* anti-surstock (couverture cible bornee) ;
* anti-surutilisation du Web (seuil de protection) ;
* anti-boucle (max iterations, pas de stock negatif, pas de doublon).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple

import numpy as np
import pandas as pd

from .parameters import Parameters
from .size_grids import GridIndex
from .transfer_scoring import Candidate, ScoredTransfer, TransferScorer


LineKey = Tuple[str, str, str, str]  # (mag, ref, coul, taille)


def _coverage(stock: float, daily: float, dormant: float) -> float:
    if daily > 0:
        return stock / daily
    return dormant if stock > 0 else 0.0


@dataclass
class OptimizerResult:
    transfers: pd.DataFrame
    blocked: List[Dict] = field(default_factory=list)
    iterations: int = 0
    stock_final: Dict[LineKey, float] = field(default_factory=dict)


class Optimizer:
    def __init__(self, base: pd.DataFrame, needs: pd.DataFrame, donors: pd.DataFrame,
                 top: pd.DataFrame, criticity: pd.DataFrame, stores: pd.DataFrame,
                 grid_index: GridIndex, distance, params: Parameters,
                 history: pd.DataFrame, today: pd.Timestamp):
        self.params = params
        self.dormant = float(params.get("couverture_dormant", 999))
        self.cible = float(params.get("couverture_cible_magasin", 30))
        self.cov_min_exp = float(params.get("couverture_min_expediteur", 20))
        self.cov_min_web = float(params.get("couverture_min_web", 30))
        self.nb_max_dest = int(params.get("nb_max_destinations", 4))
        self.seuil_score = float(params.get("seuil_score_minimum", 60))
        self.max_iter = int(params.get("max_iterations", 5000))
        self.min_coeur = int(params.get("min_tailles_coeur_receveur", 2))
        self.qte_min = float(params.get("quantite_min_transfert", 1))

        self.grid = grid_index
        self.distance = distance
        self.scorer = TransferScorer(params)

        # --- etat vivant : stock et daily par ligne ---
        self.stock: Dict[LineKey, float] = {}
        self.daily: Dict[LineKey, float] = {}
        self.picking: Dict[LineKey, float] = {}
        self.is_web: Dict[str, bool] = {}
        self.ville: Dict[str, str] = {}
        self.categorie: Dict[Tuple[str, str], str] = {}
        for row in base.itertuples(index=False):
            key = (str(row.magasin), str(row.reference), str(row.couleur), str(row.taille))
            self.stock[key] = float(getattr(row, "stock_actuel", 0) or 0)
            self.daily[key] = float(getattr(row, "moyenne_quotidienne", 0) or 0)
            self.picking[key] = float(getattr(row, "stock_transit", 0) or 0)
            self.is_web[str(row.magasin)] = bool(getattr(row, "is_web", False))
            self.ville[str(row.magasin)] = getattr(row, "ville", None)
            self.categorie[(str(row.reference), str(row.couleur))] = getattr(row, "categorie", None)

        # besoins receveur (remaining mutable)
        self.needs = needs.reset_index(drop=True).copy()
        if "qte_restante" not in self.needs:
            self.needs["qte_restante"] = self.needs["qte_besoin"]
        # suivi O(1) du besoin restant + acces au besoin par cle (perf grand volume)
        self.need_rows = list(self.needs.itertuples(index=False))
        self.remaining: Dict[LineKey, float] = {}
        self.need_by_key: Dict[LineKey, object] = {}
        for row in self.need_rows:
            key = (str(row.magasin), str(row.reference), str(row.couleur), str(row.taille))
            self.remaining[key] = float(getattr(row, "qte_restante", getattr(row, "qte_besoin", 0)))
            self.need_by_key[key] = row

        # top30 set + criticite + flagship
        self.top_set: Set[Tuple[str, str]] = set(
            zip(top["magasin"].astype(str), top["reference"].astype(str))
        ) if not top.empty else set()
        self.criticite: Dict[str, float] = dict(
            zip(criticity["magasin"].astype(str), criticity["indice_criticite"])
        ) if not criticity.empty else {}
        self.flagship: Dict[str, bool] = {}
        if stores is not None and not stores.empty and "code_magasin" in stores:
            st = stores.drop_duplicates("code_magasin")
            self.flagship = dict(zip(st["code_magasin"].astype(str), st.get("flagship", False)))

        # destinations utilisees par expediteur + paires ouvertes (anti-croise)
        self.dest_used: Dict[str, Set[str]] = {}
        self.pairs_open: Set[Tuple[str, str]] = set()
        # lignes recues durant le run (anti-chaine)
        self.received_lines: Set[LineKey] = set()

        # historique recent : paires croisees a eviter
        self.hist_pairs: Set[Tuple[str, str]] = set()
        if history is not None and not history.empty and {"expediteur", "destinataire"}.issubset(history.columns):
            delai = int(params.get("delai_protection_jours", 21))
            h = history.copy()
            if "date_transfert" in h and h["date_transfert"].notna().any():
                h = h[(today - h["date_transfert"]).dt.days <= delai * 2]
            self.hist_pairs = set(zip(h["expediteur"].astype(str), h["destinataire"].astype(str)))

        self.transfers: List[Dict] = []
        self.blocked: List[Dict] = []
        self._blocked_seen: Set[Tuple] = set()

    # --- helpers etat -------------------------------------------------------
    def _cessible(self, key: LineKey) -> float:
        """Quantite cessible par le donneur en conservant sa couverture min."""
        mag = key[0]
        stock = self.stock.get(key, 0.0)
        daily = self.daily.get(key, 0.0)
        cov_min = self.cov_min_web if self.is_web.get(mag) else self.cov_min_exp
        seuil = math.ceil(cov_min * daily) if daily > 0 else 0.0
        return max(0.0, math.floor(stock - seuil))

    def _record_blocked(self, need_row, motif: str) -> None:
        key = (str(need_row.magasin), str(need_row.reference), str(need_row.couleur),
               str(need_row.taille), motif)
        if key in self._blocked_seen:
            return
        self._blocked_seen.add(key)
        self.blocked.append({
            "magasin": str(need_row.magasin),
            "reference": str(need_row.reference),
            "couleur": str(need_row.couleur),
            "taille": str(need_row.taille),
            "qte_besoin": float(getattr(need_row, "qte_restante", need_row.qte_besoin)),
            "type_besoin": getattr(need_row, "type_besoin", ""),
            "motif_blocage": motif,
        })

    # --- construction d'un candidat -----------------------------------------
    def _build_candidate(self, need_row, donor_mag: str, qte: float,
                         reste: float | None = None) -> Candidate | None:
        if reste is None:
            reste = float(getattr(need_row, "qte_restante", 0))
        ref, coul, taille = str(need_row.reference), str(need_row.couleur), str(need_row.taille)
        rec = str(need_row.magasin)
        don_key: LineKey = (donor_mag, ref, coul, taille)
        rec_key: LineKey = (rec, ref, coul, taille)

        # --- contraintes dures ---
        if donor_mag == rec:
            return None
        # anti-chaine : ligne recue pendant le run ne peut pas re-donner
        if don_key in self.received_lines:
            return None
        # anti-croise (run + historique)
        if (rec, donor_mag) in self.pairs_open or (rec, donor_mag) in self.hist_pairs:
            self._record_blocked(need_row, "Anti-transfert croise (paire inverse existante)")
            return None
        # limite 4 destinations
        used = self.dest_used.get(donor_mag, set())
        deja_ouverte = rec in used
        if not deja_ouverte and len(used) >= self.nb_max_dest:
            self._record_blocked(need_row, f"Donneur {donor_mag} : limite de {self.nb_max_dest} destinations atteinte")
            return None

        # etats donneur avant/apres
        stock_don_avant = self.stock.get(don_key, 0.0)
        daily_don = self.daily.get(don_key, 0.0)
        stock_don_apres = stock_don_avant - qte
        if stock_don_apres < 0:
            return None
        cov_don_avant = _coverage(stock_don_avant, daily_don, self.dormant)
        cov_don_apres = _coverage(stock_don_apres, daily_don, self.dormant)

        gs_don_avant = self.grid.state(donor_mag, ref, coul)
        gs_don_apres = self.grid.state_after_remove(donor_mag, ref, coul, taille, qte)
        # anti-casse de grille cote donneur (sauf web / stock deja dormant)
        don_is_web = self.is_web.get(donor_mag, False)
        casse_grille_don = (gs_don_avant.valide and not gs_don_apres.valide)
        dormant_don = daily_don <= 0
        if casse_grille_don and not don_is_web and not dormant_don:
            # possibilite : transfert total tolere seulement si le donneur garde une grille valide
            return None

        # etats receveur avant/apres
        stock_rec_avant = self.stock.get(rec_key, 0.0)
        daily_rec = self.daily.get(rec_key, 0.0)
        stock_rec_apres = stock_rec_avant + qte
        cov_rec_avant = _coverage(stock_rec_avant, daily_rec, self.dormant)
        cov_rec_apres = _coverage(stock_rec_apres, daily_rec, self.dormant)

        gs_rec_avant = self.grid.state(rec, ref, coul)
        gs_rec_apres = self.grid.state_after_add(rec, ref, coul, taille, qte)

        # anti-casse cote receveur : la grille doit s'ameliorer ou rester valide
        type_besoin = getattr(need_row, "type_besoin", "couverture")
        if not self.is_web.get(rec, False):
            grille_amelioree = gs_rec_apres.nb_coeur > gs_rec_avant.nb_coeur
            grille_ok = gs_rec_apres.valide or grille_amelioree or gs_rec_avant.valide
            if type_besoin == "grille" and not grille_amelioree:
                self._record_blocked(need_row, "Transfert n'ameliore pas la grille")
                return None
            if not grille_ok:
                self._record_blocked(need_row, "Grille receveur resterait non conforme (<2 tailles coeur)")
                return None

        distance_km = self.distance.km(self.ville.get(donor_mag), self.ville.get(rec))

        # penalite historique : paire deja tres sollicitee
        penalite = 0.0
        if (donor_mag, rec) in self.hist_pairs:
            penalite += 0.5

        return Candidate(
            expediteur=donor_mag, destinataire=rec, reference=ref, couleur=coul,
            taille=taille, qte=qte,
            is_web_don=don_is_web,
            cov_don_avant=cov_don_avant, cov_don_apres=cov_don_apres, daily_don=daily_don,
            grid_don_avant=gs_don_avant.label(), grid_don_apres=gs_don_apres.label(),
            grid_don_valide_apres=gs_don_apres.valide,
            cov_rec_avant=cov_rec_avant, cov_rec_apres=cov_rec_apres, daily_rec=daily_rec,
            tendance_rec=getattr(need_row, "tendance", "stable"),
            grid_rec_coeur_avant=gs_rec_avant.nb_coeur, grid_rec_coeur_apres=gs_rec_apres.nb_coeur,
            grid_rec_avant=gs_rec_avant.label(), grid_rec_apres=gs_rec_apres.label(),
            type_besoin=type_besoin,
            distance_km=distance_km,
            flagship_rec=bool(self.flagship.get(rec, False)),
            criticite_rec=float(self.criticite.get(rec, 0.0)),
            dans_top30=(rec, ref) in self.top_set,
            destination_deja_ouverte=deja_ouverte,
            penalite_historique=penalite,
            stock_don_avant=stock_don_avant, stock_don_apres=stock_don_apres,
            stock_rec_avant=stock_rec_avant, stock_rec_apres=stock_rec_apres,
            besoin_residuel=float(reste),
            picking_prevu=self.picking.get(rec_key, 0.0),
        )

    def _sku_donor_index(self) -> Dict[Tuple[str, str, str], List[str]]:
        """Index (live) sku -> magasins pouvant ceder (un scan du stock)."""
        idx: Dict[Tuple[str, str, str], List[str]] = {}
        for (mag, ref, coul, taille), stock in self.stock.items():
            if stock <= 0:
                continue
            if self._cessible((mag, ref, coul, taille)) >= self.qte_min:
                idx.setdefault((ref, coul, taille), []).append(mag)
        return idx

    # --- generation de tous les candidats sur l'etat courant ----------------
    def _generate(self, record_blocked: bool = True) -> List[ScoredTransfer]:
        sku_to_donors = self._sku_donor_index()
        scored: List[ScoredTransfer] = []
        for need_row in self.need_rows:
            key = (str(need_row.magasin), str(need_row.reference),
                   str(need_row.couleur), str(need_row.taille))
            reste = self.remaining.get(key, 0.0)
            if reste < self.qte_min:
                continue
            sku = (str(need_row.reference), str(need_row.couleur), str(need_row.taille))
            donors = sku_to_donors.get(sku, [])
            if not donors:
                if record_blocked:
                    self._record_blocked(need_row, "Aucun donneur disponible pour ce besoin")
                continue
            for donor_mag in donors:
                qte = math.floor(min(reste, self._cessible((donor_mag, *sku))))
                if qte < self.qte_min:
                    continue
                cand = self._build_candidate(need_row, donor_mag, qte, reste)
                if cand is not None:
                    scored.append(self.scorer.score(cand))
        return scored

    # --- application d'un transfert -----------------------------------------
    def _apply(self, st: ScoredTransfer) -> None:
        c = st.candidate
        exp, rec = c.expediteur, c.destinataire
        don_key = (exp, c.reference, c.couleur, c.taille)
        rec_key = (rec, c.reference, c.couleur, c.taille)
        self.stock[don_key] = self.stock.get(don_key, 0.0) - c.qte
        self.stock[rec_key] = self.stock.get(rec_key, 0.0) + c.qte
        self.grid.apply_move(exp, rec, c.reference, c.couleur, c.taille, c.qte)
        self.dest_used.setdefault(exp, set()).add(rec)
        self.pairs_open.add((exp, rec))
        self.received_lines.add(rec_key)

        # reduire le besoin correspondant (O(1))
        self.remaining[rec_key] = max(0.0, self.remaining.get(rec_key, 0.0) - c.qte)

        self.transfers.append({
            "score": st.score,
            "priorite": st.priorite,
            "expediteur": exp,
            "destinataire": rec,
            "reference": c.reference,
            "couleur": c.couleur,
            "taille": c.taille,
            "quantite": c.qte,
            "stock_exp_avant": c.stock_don_avant,
            "stock_exp_apres": c.stock_don_apres,
            "cov_exp_avant": round(c.cov_don_avant, 1),
            "cov_exp_apres": round(c.cov_don_apres, 1),
            "stock_dest_avant": c.stock_rec_avant,
            "stock_dest_apres": c.stock_rec_apres,
            "cov_dest_avant": round(c.cov_rec_avant, 1),
            "cov_dest_apres": round(c.cov_rec_apres, 1),
            "grille_avant": c.grid_rec_avant,
            "grille_apres": c.grid_rec_apres,
            "picking_prevu": c.picking_prevu,
            "besoin_residuel": c.besoin_residuel,
            "motif": st.motif,
            "distance_km": round(c.distance_km, 0),
            "type_besoin": c.type_besoin,
            "is_web_don": c.is_web_don,
        })

    # --- boucle principale (iteratif fidele au brief, module 10) ------------
    def run(self, fast: bool = False) -> OptimizerResult:
        if fast:
            return self._run_fast()
        iterations = 0
        while iterations < self.max_iter:
            candidates = self._generate()
            if not candidates:
                break
            candidates.sort(key=lambda s: s.score, reverse=True)
            best = candidates[0]
            if best.score < self.seuil_score:
                break
            self._apply(best)
            iterations += 1
        return self._finalize(iterations)

    # --- variante grand volume : pre-scoring + une passe de faisabilite -----
    def _run_fast(self) -> OptimizerResult:
        """Scoring de tous les candidats une fois, puis application dans l'ordre
        de score en re-validant chaque transfert sur l'etat courant (stocks,
        grilles, limite 4 destinations, anti-croise). Adapte aux gros volumes :
        evite de re-scanner tout le stock a chaque transfert."""
        candidates = self._generate()
        candidates.sort(key=lambda s: s.score, reverse=True)
        applied = 0
        for st in candidates:
            if applied >= self.max_iter:
                break
            c = st.candidate
            rec_key = (c.destinataire, c.reference, c.couleur, c.taille)
            reste = self.remaining.get(rec_key, 0.0)
            if reste < self.qte_min:
                continue
            qte = math.floor(min(reste, self._cessible(
                (c.expediteur, c.reference, c.couleur, c.taille))))
            if qte < self.qte_min:
                continue
            need_row = self.need_by_key.get(rec_key)
            if need_row is None:
                continue
            live = self._build_candidate(need_row, c.expediteur, qte, reste)
            if live is None:
                continue
            st_live = self.scorer.score(live)
            if st_live.score < self.seuil_score:
                continue
            self._apply(st_live)
            applied += 1
        return self._finalize(applied)

    # --- finalisation partagee ----------------------------------------------
    def _finalize(self, iterations: int) -> OptimizerResult:
        # synchronise le besoin restant pour l'onglet "cas non traites"
        if "qte_restante" in self.needs.columns and self.remaining:
            self.needs["qte_restante"] = [
                self.remaining.get((str(r.magasin), str(r.reference),
                                    str(r.couleur), str(r.taille)),
                                   getattr(r, "qte_restante", 0))
                for r in self.needs.itertuples(index=False)
            ]

        # destinations numerotees pour chaque expediteur
        dest_rank: Dict[str, Dict[str, int]] = {}
        for exp, dests in self.dest_used.items():
            for i, d in enumerate(sorted(dests), start=1):
                dest_rank.setdefault(exp, {})[d] = i
        for t in self.transfers:
            t["destination_num"] = dest_rank.get(t["expediteur"], {}).get(t["destinataire"], 1)

        transfers_df = pd.DataFrame(self.transfers)
        return OptimizerResult(
            transfers=transfers_df,
            blocked=self.blocked,
            iterations=iterations,
            stock_final=dict(self.stock),
        )
