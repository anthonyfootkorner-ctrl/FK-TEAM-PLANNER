"""Valorisation cumulative des reassorts (argent genere par les pieces bougees).

Deux pistes SEPAREES :
 * ``central``    : reassort CENTRAL -> magasin ;
 * ``interstore`` : transfert magasin -> magasin (credite a l'EXPEDITEUR autant
   qu'au destinataire — « l'argent que mes envois ont rapporte ailleurs »).

Modele (regles validees avec le metier) :
 * on compte les ventes a destination sur la reference envoyee, a partir de la
   date du reassort (AUCUN delai : un magasin ne peut pas vendre ce qu'il n'a
   pas encore recu, donc pas de fausse attribution) ;
 * cumul SANS limite de temps, PLAFONNE au nombre de pieces envoyees (on ne
   credite jamais plus que ce qu'on a bouge) ;
 * ``last_date`` (derniere date de vente comptee) evite le double comptage entre
   deux fichiers de ventes qui se recouvrent (fenetres de 35 j, cadence hebdo).

Une « cohorte » = (run source, type, expediteur, destinataire, reference). Pour
ne pas compter deux fois la meme vente, une seule cohorte OUVERTE par
(type, destinataire, reference) accumule a la fois : creer une nouvelle cohorte
sur la meme cle ferme la precedente (qui garde sa valeur acquise).
"""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional

import pandas as pd

CENTRAL = "CENTRAL"


def _pa_map(stocks) -> dict:
    if stocks is None or getattr(stocks, "empty", True) or "prix_achat" not in getattr(stocks, "columns", []):
        return {}
    s = stocks[stocks["prix_achat"] > 0]
    if s.empty:
        return {}
    return s.groupby("reference")["prix_achat"].median().to_dict()


def build_new_cohorts(source_run_id: str, run_date, reassort_central,
                      transfers) -> List[Dict]:
    """Construit les cohortes d'un nouveau run (cumul 0, a accumuler ensuite).

    ``reassort_central`` : DataFrame (boutique, barcode/reference, qte_proposee).
    ``transfers`` : liste de dicts (expediteur, destinataire, reference, quantite)
    ou DataFrame equivalent.
    """
    rows: List[Dict] = []
    rd = str(pd.Timestamp(run_date).date()) if run_date is not None else None

    # -- central : CENTRAL -> boutique --
    if reassort_central is not None and not getattr(reassort_central, "empty", True):
        rc = reassort_central.copy()
        refcol = "reference" if "reference" in rc.columns else "barcode"
        rc["qsum"] = pd.to_numeric(rc.get("qte_proposee", 0), errors="coerce").fillna(0.0)
        g = rc.groupby(["boutique", refcol], as_index=False)["qsum"].sum()
        for r in g.itertuples(index=False):
            q = int(getattr(r, "qsum"))
            if q <= 0:
                continue
            rows.append(_cohort(source_run_id, "central", CENTRAL,
                                str(r.boutique), str(getattr(r, refcol)), q, rd))

    # -- interstore : magasin -> magasin --
    tdf = pd.DataFrame(transfers) if transfers is not None else pd.DataFrame()
    if not tdf.empty and {"expediteur", "destinataire", "reference"}.issubset(tdf.columns):
        tdf["qsum"] = pd.to_numeric(tdf.get("quantite", 0), errors="coerce").fillna(0.0)
        g = tdf.groupby(["expediteur", "destinataire", "reference"], as_index=False)["qsum"].sum()
        for r in g.itertuples(index=False):
            q = int(getattr(r, "qsum"))
            if q <= 0:
                continue
            rows.append(_cohort(source_run_id, "interstore", str(r.expediteur),
                                str(r.destinataire), str(r.reference), q, rd))
    return rows


def _cohort(run_id, typ, exp, dest, ref, qty, run_date) -> Dict:
    return {
        "source_run_id": run_id, "type": typ, "expediteur": exp,
        "destinataire": dest, "reference": ref, "sent_qty": qty,
        "run_date": run_date, "cumul_units": 0, "cumul_ca": 0.0,
        "cumul_marge": 0.0, "last_date": run_date, "closed": False,
    }


def cohorts_to_close(new_cohorts: List[Dict], existing_open: List[Dict]) -> List:
    """Ids des cohortes ouvertes a fermer : une nouvelle cohorte sur la meme cle
    (type, destinataire, reference) remplace l'ancienne (evite le double comptage)."""
    keys = {(c["type"], c["destinataire"], c["reference"]) for c in new_cohorts}
    return [c["id"] for c in existing_open
            if "id" in c and (c["type"], c["destinataire"], c["reference"]) in keys]


def accumulate(open_rows: List[Dict], ventes_detail, stocks,
               tva: float = 1.2, ratio_achat: float = 2.3) -> List[Dict]:
    """Fait avancer les cohortes ouvertes avec les nouvelles ventes.

    Renvoie la liste des cohortes MODIFIEES (memes cles + nouveaux cumuls +
    ``last_date`` + ``closed``), pretes a etre mises a jour en base.
    """
    if not open_rows or ventes_detail is None or getattr(ventes_detail, "empty", True):
        return []
    v = ventes_detail.copy()
    if "date" not in v.columns:
        return []
    v["date"] = pd.to_datetime(v["date"], errors="coerce")
    v = v[v["date"].notna()]
    if v.empty:
        return []
    vmax = v["date"].max()
    vmax_d = str(vmax.date())
    pa = _pa_map(stocks)

    # regroupe les cohortes par last_date (peu de valeurs distinctes -> efficace)
    by_ld: Dict[Optional[str], List[Dict]] = defaultdict(list)
    for r in open_rows:
        if r.get("closed"):
            continue
        by_ld[r.get("last_date")].append(r)

    updated: List[Dict] = []
    for ld, rows in by_ld.items():
        vv = v[v["date"] > pd.Timestamp(ld)] if ld else v
        sold = {}
        if not vv.empty:
            agg = vv.groupby(["magasin", "reference"], as_index=False).agg(
                units=("qte", "sum"), ca=("ca", "sum"))
            sold = {(str(x.magasin), str(x.reference)): (float(x.units), float(x.ca))
                    for x in agg.itertuples(index=False)}
        for r in rows:
            dest, ref = str(r["destinataire"]), str(r["reference"])
            sent = float(r["sent_qty"])
            cu = float(r["cumul_units"])
            remaining = max(0.0, sent - cu)
            u, c = sold.get((dest, ref), (0.0, 0.0))
            changed = False
            if remaining > 0 and u > 0:
                att = min(remaining, u)
                pu_ttc = c / u if u else 0.0
                pau = pa.get(ref)
                if not pau or pau <= 0:
                    pau = pu_ttc / ratio_achat
                r2 = dict(r)
                r2["cumul_units"] = int(round(cu + att))
                r2["cumul_ca"] = round(float(r["cumul_ca"]) + att * pu_ttc, 2)
                r2["cumul_marge"] = round(float(r["cumul_marge"]) + att * (pu_ttc / tva - pau), 2)
                r2["last_date"] = vmax_d
                r2["closed"] = r2["cumul_units"] >= sent
                updated.append(r2)
                changed = True
            if not changed and ld != vmax_d:
                # rien vendu ce cycle : on avance quand meme la date (anti double compte)
                r2 = dict(r)
                r2["last_date"] = vmax_d
                updated.append(r2)
    return updated


def summarize(rows: List[Dict]) -> Dict:
    """Agrege des cohortes en totaux par piste / magasin (pour l'affichage)."""
    out = {
        "central": {"units": 0, "ca": 0.0, "marge": 0.0, "par_dest": {}},
        "interstore": {"units": 0, "ca": 0.0, "marge": 0.0,
                       "par_expediteur": {}, "par_dest": {}},
    }
    for r in rows or []:
        t = r.get("type")
        if t not in out:
            continue
        u, ca, m = int(r.get("cumul_units", 0)), float(r.get("cumul_ca", 0)), float(r.get("cumul_marge", 0))
        out[t]["units"] += u
        out[t]["ca"] += ca
        out[t]["marge"] += m
        _add(out[t]["par_dest"], r.get("destinataire"), u, ca, m)
        if t == "interstore":
            _add(out[t]["par_expediteur"], r.get("expediteur"), u, ca, m)
    for t in out:
        out[t]["ca"] = round(out[t]["ca"])
        out[t]["marge"] = round(out[t]["marge"])
        for grp in ("par_dest", "par_expediteur"):
            if grp in out[t]:
                out[t][grp] = {k: {"units": v["units"], "ca": round(v["ca"]), "marge": round(v["marge"])}
                               for k, v in out[t][grp].items()}
    return out


def _add(d: dict, key, u, ca, m):
    if not key:
        return
    e = d.setdefault(str(key), {"units": 0, "ca": 0.0, "marge": 0.0})
    e["units"] += u
    e["ca"] += ca
    e["marge"] += m
