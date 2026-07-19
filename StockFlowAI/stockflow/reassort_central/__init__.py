"""Reassort central (CENTRAL -> boutiques) et chainage vers le picking.

Ce module encapsule le moteur d'approvisionnement historique
(``agent_reassort_multiboutiques.py``, vendorise tel quel dans :mod:`agent`)
et l'expose derriere une API propre, sans effet de bord (ni interface
graphique, ni e-mail, ni PDF).

Enchainement demande par le metier (« A + B ») :

1. **Reassort central** : on calcule d'abord les transferts CENTRAL -> boutiques
   (couverture cible, filtres promo / saison, regles de grille de tailles),
   via :func:`compute_reassort_central`.
2. **Chainage picking** : la sortie du reassort central est convertie en
   *picking* (stock EN TRANSIT vers la boutique) par :func:`proposed_to_picking`,
   puis injectee dans le moteur de transferts inter-magasins StockFlow. Celui-ci
   calcule donc un besoin residuel NET du reassort central (pas de double
   comptage — meme logique que ``ingest_real.load_reassort``).
3. **Sorties** : A = table « Reassort central » (proposals brutes) ;
   B = fichier d'import Fastmag (:func:`build_fastmag_import`).

Les fichiers d'entree sont ceux deja utilises par StockFlow (exports Fastmag
``Code_Origine`` / ``BarCode V2`` / ``Total Stock`` / ``Total QteVenteRetail``),
plus un export du **stock CENTRAL** (TSV ``Reference`` / ``Taille`` / ``Stock``).
La ``Reference`` du stock CENTRAL et le ``BarCode V2`` des boutiques partagent
le meme identifiant (ex. ``0200NZ-010``), qui est aussi la ``reference`` de
StockFlow : le chainage joint donc proprement.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd

from ..parameters import Parameters
from ..ingest_real import _norm_sizes, barcode_reference
from . import agent as _ag

DEFAULT_RESERVE = _ag.DEFAULT_RESERVE
DEFAULT_TARGET_DAYS = _ag.DEFAULT_TARGET_DAYS
DEFAULT_SALES_DAYS = _ag.DEFAULT_SALES_DAYS


# ---------------------------------------------------------------------------
# Resultat
# ---------------------------------------------------------------------------
@dataclass
class ReassortCentralResult:
    proposed: pd.DataFrame = field(default_factory=pd.DataFrame)
    risk: pd.DataFrame = field(default_factory=pd.DataFrame)
    promo_exclus: pd.DataFrame = field(default_factory=pd.DataFrame)
    taille_seule_exclus: pd.DataFrame = field(default_factory=pd.DataFrame)
    top: pd.DataFrame = field(default_factory=pd.DataFrame)
    reserve: str = DEFAULT_RESERVE
    target_days: int = DEFAULT_TARGET_DAYS
    sales_days: int = DEFAULT_SALES_DAYS
    sales_start: str = ""
    sales_end: str = ""
    central_total: int = 0
    summary: Dict[str, Any] = field(default_factory=dict)
    message: str = ""
    # frames au format agent, conserves pour la 2e passe (completion de grille
    # apres l'inter-magasins) : stock boutiques+CENTRAL et ventes agregees.
    stock_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    ventes_df: pd.DataFrame = field(default_factory=pd.DataFrame)

    @property
    def ok(self) -> bool:
        return not self.proposed.empty


# ---------------------------------------------------------------------------
# Lecture des fichiers (chemin OU fichier-memoire / upload navigateur)
# ---------------------------------------------------------------------------
def _to_bytes(src) -> Optional[bytes]:
    if src is None:
        return None
    if isinstance(src, (bytes, bytearray)):
        return bytes(src)
    if hasattr(src, "read"):
        try:
            src.seek(0)
        except Exception:
            pass
        return src.read()
    return Path(src).read_bytes()


def _read_csv_bytes(data: bytes) -> pd.DataFrame:
    """Lit un CSV (exports StockFlow, separateur virgule) en essayant les
    encodages courants ; neutralise le BOM."""
    last = None
    for enc in ("utf-8-sig", "utf-8", "latin1"):
        try:
            return pd.read_csv(io.BytesIO(data), dtype=str,
                               keep_default_na=False, na_values=[""], encoding=enc)
        except UnicodeDecodeError as exc:
            last = exc
            continue
    raise ValueError(f"Fichier CSV illisible : {last}")


# Ces chargeurs reproduisent fidelement agent.load_stock / agent.load_ventes,
# mais lisent depuis des octets (upload) et conservent la taille BRUTE
# (indispensable aux regles de grille : _is_core_size, plages de pointures).
_C_BOUTIQUE = ["Code_Origine", "Magasin", "Boutique", "Code_Magasin"]
_C_BARCODE = ["BarCode V2", "Barcode", "Code barre", "Gencod", "GenCod", "EAN"]
_C_TAILLE = ["Taille", "Size", "Pointure"]
_C_STOCK = ["Total Stock", "Stock", "Quantité disponible", "Quantite disponible", "Qte"]
_C_QTY = ["Total QteVenteRetail", "QteVenteRetail", "Quantite", "Quantité", "Ventes", "Qte"]
_C_DATE = ["Jours dans Date", "Date", "Jour"]
_C_MARQUE = ["Marque Gp", "Marque", "Brand"]
_C_SAISON = ["Saison", "Season"]
_C_PRIX = ["PrixVente", "Prix vente", "Prix_vente", "PV"]
_C_MT = ["MtVenteRetailTTC", "Total MtVenteRetailTTC", "MontantVente", "CA TTC", "MtVente"]


def _load_stock_df(data: bytes, reserve: str) -> pd.DataFrame:
    df = _read_csv_bytes(data)
    df.columns = [_ag.clean_col(c) for c in df.columns]
    bcol = _ag.find_col(df, _C_BOUTIQUE)
    barcol = _ag.find_col(df, _C_BARCODE)
    tcol = _ag.find_col(df, _C_TAILLE)
    scol = _ag.find_col(df, _C_STOCK)
    missing = [n for n, c in (("boutique", bcol), ("barcode", barcol),
                              ("taille", tcol), ("stock", scol)) if not c]
    if missing:
        raise ValueError(f"Fichier STOCK : colonne(s) manquante(s) {missing}. "
                         f"Colonnes trouvees : {list(df.columns)[:20]}")
    out = pd.DataFrame({
        "boutique": df[bcol].astype(str).str.strip(),
        "barcode": df[barcol].astype(str).str.strip(),
        "taille": df[tcol].astype(str).str.strip(),
        "stock": _ag.to_number(df[scol]),
    })
    out = out[out["barcode"].notna() & (out["barcode"] != "") & (out["barcode"] != "nan")]
    return out.groupby(["boutique", "barcode", "taille"], as_index=False)["stock"].sum()


def _load_ventes_df(data: bytes, default_sales_days: int):
    df = _read_csv_bytes(data)
    df.columns = [_ag.clean_col(c) for c in df.columns]
    bcol = _ag.find_col(df, _C_BOUTIQUE)
    barcol = _ag.find_col(df, _C_BARCODE)
    tcol = _ag.find_col(df, _C_TAILLE)
    qcol = _ag.find_col(df, _C_QTY)
    dcol = _ag.find_col(df, _C_DATE)
    mcol = _ag.find_col(df, _C_MARQUE)
    scol = _ag.find_col(df, _C_SAISON)
    pcol = _ag.find_col(df, _C_PRIX)
    mtcol = _ag.find_col(df, _C_MT)
    missing = [n for n, c in (("boutique", bcol), ("barcode", barcol),
                              ("taille", tcol), ("quantite", qcol)) if not c]
    if missing:
        raise ValueError(f"Fichier VENTES : colonne(s) manquante(s) {missing}. "
                         f"Colonnes trouvees : {list(df.columns)[:20]}")
    out = pd.DataFrame({
        "boutique": df[bcol].astype(str).str.strip(),
        "barcode": df[barcol].astype(str).str.strip(),
        "taille": df[tcol].astype(str).str.strip(),
        "qty": _ag.to_number(df[qcol]),
    })
    if mcol:
        out["marque"] = df[mcol].astype(str).str.strip()
    if scol:
        out["saison"] = df[scol].astype(str).str.strip()
    if pcol:
        out["prix_vente"] = _ag.to_number(df[pcol])
    if mtcol:
        out["mt_realise"] = _ag.to_number(df[mtcol])

    sales_days = default_sales_days
    start_date, end_date = "", ""
    if dcol:
        dates = pd.to_datetime(df[dcol], dayfirst=True, errors="coerce")
        if dates.notna().any():
            start_date = dates.min().strftime("%d/%m/%Y")
            end_date = dates.max().strftime("%d/%m/%Y")
            actual = (dates.max() - dates.min()).days + 1
            if actual >= 7:
                sales_days = actual

    out = out[out["barcode"].notna() & (out["barcode"] != "") & (out["barcode"] != "nan")]
    return out, start_date, end_date, sales_days


def _load_central_df(data: bytes, reserve: str) -> pd.DataFrame:
    """Charge le stock CENTRAL depuis un export dedie (TSV latin1
    ``Reference`` / ``Taille`` / ``Stock``, ou xlsx/csv equivalent).

    Reproduit la logique de ``main()`` du moteur historique : le stock CENTRAL
    provient d'un export distinct, indexe par ``Reference`` (= BarCode V2)."""
    df = None
    for reader in (
        lambda: pd.read_csv(io.BytesIO(data), sep="\t", encoding="latin1", dtype=str),
        lambda: pd.read_csv(io.BytesIO(data), sep=None, engine="python",
                            encoding="latin1", dtype=str),
        lambda: pd.read_excel(io.BytesIO(data), dtype=str),
    ):
        try:
            cand = reader()
            if cand is not None and cand.shape[1] >= 3:
                df = cand
                break
        except Exception:
            continue
    if df is None:
        raise ValueError("Stock CENTRAL illisible (attendu : TSV/xlsx Reference/Taille/Stock).")
    df.columns = [_ag.clean_col(c) for c in df.columns]

    ref_col = _ag.find_col(df, ["Référence", "Reference", "Réf", "Ref", "BarCode V2", "Barcode"])
    taille_col = _ag.find_col(df, _C_TAILLE)
    stock_col = _ag.find_col(df, ["Stock", "Total Stock", "Qte", "Quantité"])
    if not (ref_col and taille_col and stock_col):
        raise ValueError(
            f"Stock CENTRAL : colonnes Reference/Taille/Stock introuvables. "
            f"Colonnes trouvees : {list(df.columns)[:20]}")
    out = pd.DataFrame({
        "boutique": reserve,
        "barcode": df[ref_col].astype(str).str.strip(),
        "taille": df[taille_col].astype(str).str.strip(),
        "stock": _ag.to_number(df[stock_col]),
    })
    out = out[out["barcode"].notna() & (out["barcode"] != "") & (out["barcode"] != "nan")]
    return out.groupby(["boutique", "barcode", "taille"], as_index=False)["stock"].sum()


# ---------------------------------------------------------------------------
# API principale
# ---------------------------------------------------------------------------
def compute_reassort_central(
    *,
    stock,
    ventes,
    central_stock=None,
    params: Optional[Parameters] = None,
    target_days: Optional[int] = None,
    sales_days: int = DEFAULT_SALES_DAYS,
    promo_seuil: float = 0.20,
    reserve: str = DEFAULT_RESERVE,
) -> ReassortCentralResult:
    """Calcule le reassort central CENTRAL -> boutiques.

    ``stock`` / ``ventes`` : exports StockFlow (chemin ou fichier-memoire).
    ``central_stock`` : export du stock CENTRAL (optionnel). S'il est absent, on
    utilise les lignes ``CENTRAL`` deja presentes dans le fichier stock.
    """
    p = params or Parameters()
    if target_days is None:
        target_days = int(p.get("couverture_cible_central") or DEFAULT_TARGET_DAYS)

    stock_df = _load_stock_df(_to_bytes(stock), reserve)
    ventes_df, s0, s1, sd = _load_ventes_df(_to_bytes(ventes), sales_days)

    cb = _to_bytes(central_stock)
    if cb is not None:
        central_rows = _load_central_df(cb, reserve)
        stock_df = pd.concat(
            [stock_df[stock_df["boutique"] != reserve], central_rows],
            ignore_index=True)

    reserve_total = int(stock_df.loc[stock_df["boutique"] == reserve, "stock"].sum())
    if reserve not in set(stock_df["boutique"].unique()) or reserve_total <= 0:
        return ReassortCentralResult(
            reserve=reserve, target_days=target_days, sales_days=sd,
            sales_start=s0, sales_end=s1, central_total=reserve_total,
            message=(f"Reserve « {reserve} » absente ou vide : aucun reassort central "
                     f"possible (fournir un export du stock CENTRAL)."))

    promo_df = _ag.compute_promo_rates(ventes_df, threshold=promo_seuil)
    proposed, risk, top, promo_exclus, taille_seule = _ag.run_agent(
        stock_df, ventes_df, reserve, target_days, sd,
        promo_df=promo_df, promo_seuil=promo_seuil,
    )

    total_qte = int(proposed["qte_proposee"].sum()) if not proposed.empty else 0
    summary = {
        "lignes": int(len(proposed)),
        "pieces": total_qte,
        "risques": int(len(risk)),
        "promo_exclus": int(len(promo_exclus)),
        "tailles_isolees": int(len(taille_seule)),
        "central_pieces": reserve_total,
        "boutiques": (int(proposed["boutique"].nunique()) if not proposed.empty else 0),
    }
    return ReassortCentralResult(
        proposed=proposed, risk=risk, promo_exclus=promo_exclus,
        taille_seule_exclus=taille_seule, top=top,
        reserve=reserve, target_days=target_days, sales_days=sd,
        sales_start=s0, sales_end=s1, central_total=reserve_total,
        summary=summary, stock_df=stock_df, ventes_df=ventes_df,
        message=(f"{summary['lignes']} lignes, {summary['pieces']} pieces vers "
                 f"{summary['boutiques']} boutiques."))


def apply_exclusions(res: "ReassortCentralResult", refs) -> "ReassortCentralResult":
    """Retire du reassort central les references exclues (liste utilisateur).

    Correspondance sur la reference (= ``barcode_reference`` du BarCode V2) exacte
    OU sur le modele (partie avant le tiret). Met a jour ``proposed`` et les
    compteurs du ``summary`` pour que l'Excel et l'e-mail recap restent justes."""
    from ..exclusions import excluded_mask, to_set
    exset = to_set(refs)
    if not exset or res is None or res.proposed is None or res.proposed.empty:
        return res
    prop = res.proposed
    ref = barcode_reference(prop["barcode"])
    keep = ~excluded_mask(ref, exset)
    res.proposed = prop[keep].copy()
    total_qte = int(res.proposed["qte_proposee"].sum()) if not res.proposed.empty else 0
    res.summary = dict(res.summary or {})
    res.summary["lignes"] = int(len(res.proposed))
    res.summary["pieces"] = total_qte
    res.summary["boutiques"] = (int(res.proposed["boutique"].nunique())
                                if not res.proposed.empty else 0)
    res.summary["references_exclues"] = int(sum(~keep))
    res.message = (f"{res.summary['lignes']} lignes, {res.summary['pieces']} pieces vers "
                   f"{res.summary['boutiques']} boutiques.")
    return res


def complete_grids_after_transfers(res: "ReassortCentralResult",
                                   transfers: pd.DataFrame,
                                   params: Optional[Parameters] = None) -> pd.DataFrame:
    """2e passe du reassort central, APRES l'inter-magasins.

    Le central retient (« courbe de tailles rompue ») les tailles qu'il ne peut
    pas assembler seul en grille valide. Une fois l'inter-magasins passe, une
    boutique peut avoir recu d'autres tailles : la taille retenue par le central
    completerait alors une grille valide. On rejoue donc le filtre de grille du
    central (memes regles) mais avec le stock boutique AUGMENTE des tailles
    recues (reassort central pass 1 + transferts inter-magasins), en puisant
    uniquement dans le stock CENTRAL restant. Retourne les lignes de reassort
    central SUPPLEMENTAIRES (meme schema que ``proposed``)."""
    empty = pd.DataFrame()
    if res is None:
        return empty
    withheld = res.taille_seule_exclus
    stock_df = res.stock_df
    ventes_df = res.ventes_df
    if (withheld is None or withheld.empty or stock_df is None or stock_df.empty
            or "barcode" not in getattr(withheld, "columns", [])):
        return empty
    reserve = res.reserve

    # 1) stock CENTRAL restant apres la 1re passe (total - deja propose)
    reserve_total = (stock_df[stock_df["boutique"] == reserve]
                     .groupby(["barcode", "taille"])["stock"].sum())
    alloc = pd.Series(dtype=float)
    if res.proposed is not None and not res.proposed.empty:
        alloc = res.proposed.groupby(["barcode", "taille"])["qte_proposee"].sum()
    rem: Dict = {}
    for (bc, t), q in reserve_total.items():
        rem[(str(bc), str(t))] = int(max(0, float(q) - float(alloc.get((bc, t), 0))))

    # 2) stock boutique augmente : + reassort central pass 1 + transferts recus
    adds = []
    if res.proposed is not None and not res.proposed.empty:
        for r in res.proposed.itertuples(index=False):
            adds.append({"boutique": str(r.boutique), "barcode": str(r.barcode),
                         "taille": str(r.taille), "stock": float(r.qte_proposee)})
    if transfers is not None and not transfers.empty:
        cols = set(transfers.columns)
        for r in transfers.itertuples(index=False):
            if {"destinataire", "reference", "taille", "quantite"} <= cols:
                adds.append({"boutique": str(r.destinataire), "barcode": str(r.reference),
                             "taille": str(r.taille), "stock": float(r.quantite)})
    aug = stock_df[["boutique", "barcode", "taille", "stock"]].copy()
    if adds:
        aug = pd.concat([aug, pd.DataFrame(adds)], ignore_index=True)
    aug = aug.groupby(["boutique", "barcode", "taille"], as_index=False)["stock"].sum()

    # tailles deja couvertes (stock magasin + pass 1 + inter-magasins) : on ne
    # renvoie jamais une taille deja servie a la boutique.
    covered = {(str(r.boutique), str(r.barcode), str(r.taille))
               for r in aug[aug["stock"] > 0].itertuples(index=False)}

    # 3) allouer les tailles retenues depuis le CENTRAL restant, par priorite
    def _pn(s):
        m = re.search(r"P(\d)", str(s))
        return int(m.group(1)) if m else 9
    w = withheld.copy()
    w["_pn"] = w["priorite"].apply(_pn) if "priorite" in w.columns else 9
    w = w.sort_values("_pn")
    keep_cols = [c for c in withheld.columns if c != "raison_exclusion"]
    rows = []
    # to_dict : itertuples mangle les colonnes a underscore (_is_core, ...)
    for rec in w.to_dict("records"):
        key = (str(rec["boutique"]), str(rec["barcode"]), str(rec["taille"]))
        if key in covered:
            continue
        avail = rem.get((str(rec["barcode"]), str(rec["taille"])), 0)
        give = min(int(rec.get("qte_proposee", 0) or 0), avail)
        if give <= 0:
            continue
        rem[(str(rec["barcode"]), str(rec["taille"]))] = avail - give
        d = {c: rec.get(c) for c in keep_cols}
        d["qte_proposee"] = give
        rows.append(d)
    if not rows:
        return empty
    candidates = pd.DataFrame(rows)

    # 4) rejouer le filtre de grille du central avec le stock augmente : ne
    #    survivent que les tailles qui forment desormais une grille valide.
    clean, _excl = _ag._filter_tailles_isolees(
        candidates, aug, ventes_df, reserve=reserve, reserve_pool=rem)
    if clean is None or clean.empty:
        return empty
    mask = [(str(r.boutique), str(r.barcode), str(r.taille)) not in covered
            for r in clean.itertuples(index=False)]
    clean = clean[pd.Series(mask, index=clean.index)].copy()
    if clean.empty:
        return empty
    clean["priorite"] = "P4 - 2e passe"
    clean["commentaire"] = "2e passe : grille completee apres inter-magasins"
    return clean.reset_index(drop=True)


def proposed_to_picking(proposed: pd.DataFrame) -> pd.DataFrame:
    """Convertit la sortie du reassort central en *picking* StockFlow (stock en
    transit vers la boutique destinataire).

    Colonnes de sortie identiques a ``ingest_real.load_reassort`` :
    ``magasin, reference, couleur, taille, quantite_prevue, statut_reassort,
    id_mouvement``. La ``reference`` est le code-barre complet (= BarCode V2 =
    reference StockFlow) ; la taille est normalisee comme le reste du moteur."""
    if proposed is None or proposed.empty:
        return pd.DataFrame()
    ref = barcode_reference(proposed["barcode"])
    taille, _ = _norm_sizes(proposed["taille"])
    qte = pd.to_numeric(proposed["qte_proposee"], errors="coerce").fillna(0.0)
    pick = pd.DataFrame({
        "magasin": proposed["boutique"].astype(str).str.strip(),
        "reference": ref,
        "couleur": "",
        "taille": taille,
        "quantite_prevue": qte,
        "statut_reassort": "PROPOSE",       # non receptionne => en transit
        "id_mouvement": [f"RC{i:05d}" for i in range(len(proposed))],
    })
    pick = pick[pick["quantite_prevue"] > 0]
    if pick.empty:
        return pd.DataFrame()
    pick = pick.groupby(["magasin", "reference", "couleur", "taille"], as_index=False).agg(
        quantite_prevue=("quantite_prevue", "sum"),
        statut_reassort=("statut_reassort", "first"),
        id_mouvement=("id_mouvement", "first"))
    return pick


def build_reassort_excel(res: "ReassortCentralResult", out_path) -> bool:
    """Genere le classeur Excel recap (comme l'outil historique) : Synthese,
    Tous transferts, une feuille par magasin, alertes, risques, top ventes."""
    if res is None or res.proposed is None or res.proposed.empty:
        return False
    _ag.build_excel(
        Path(out_path), res.proposed, res.risk, res.top,
        res.promo_exclus, res.taille_seule_exclus, res.reserve,
        res.sales_start, res.sales_end, res.target_days, res.sales_days)
    return True


def build_reassort_email_html(res: "ReassortCentralResult", run_date=None) -> str:
    """Corps HTML du mail recap (reprend le format de l'outil historique)."""
    if res is None or res.proposed is None or res.proposed.empty:
        return ""
    return _ag.build_email_html(
        res.proposed, res.risk, res.promo_exclus, res.taille_seule_exclus,
        res.sales_start, res.sales_end, res.target_days, res.sales_days,
        res.reserve, run_date=run_date)


def build_fastmag_import(proposed: pd.DataFrame, out_path, ref_dir,
                         run_date=None) -> tuple[int, int, list]:
    """Genere le fichier d'import Fastmag (sortie B).

    ``ref_dir`` doit contenir les fichiers de reference : ``Footkorner -
    Listing mag.xlsx`` (code mag -> NUM, indispensable), ``prix de gros.csv``
    (PU, optionnel), ``fastmag_bdd.xls`` (designation/couleur, optionnel),
    ``stock_central.xls`` (couleur reelle CENTRAL, optionnel).
    Retourne ``(nb_lignes, nb_boutiques, boutiques_sans_num)``."""
    if proposed is None or proposed.empty:
        return 0, 0, []
    return _ag.generate_fastmag_import(
        proposed, Path(out_path), Path(ref_dir), run_date=run_date)
