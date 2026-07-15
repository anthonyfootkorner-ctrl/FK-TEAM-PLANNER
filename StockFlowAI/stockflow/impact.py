"""Mesure d'impact : ventes realisees sur les references transferees.

A chaque generation, on compare les transferts du run PRECEDENT aux ventes de
la nouvelle periode (chez le magasin destinataire) et on estime :
 - le nombre d'articles vendus attribues au transfert (plafonne a la quantite
   envoyee : on ne credite pas plus que ce qu'on a deplace) ;
 - le CA (TTC) genere ;
 - la marge (prix de vente HT - prix d'achat).

C'est une ESTIMATION : on ne peut pas savoir si une piece vendue provient du
stock transfere ou du stock deja present ; le plafonnement rend le credit
prudent.
"""

from __future__ import annotations

import pandas as pd


def compute_impact(prev_transfers, ventes_detail, stocks, since_date=None,
                   tva: float = 1.2, ratio_achat: float = 2.3) -> dict:
    empty = {"units": 0, "ca": 0.0, "marge": 0.0, "par_magasin": {}}
    if not prev_transfers or ventes_detail is None or getattr(ventes_detail, "empty", True):
        return empty

    v = ventes_detail.copy()
    if since_date is not None and "date" in v.columns:
        v = v[v["date"] >= pd.Timestamp(since_date)]
    if v.empty:
        return empty

    g = v.groupby(["magasin", "reference"], as_index=False).agg(
        units=("qte", "sum"), ca=("ca", "sum"))
    g = g[g["units"] > 0]
    sold = {(str(r.magasin), str(r.reference)): (float(r.units), float(r.ca))
            for r in g.itertuples(index=False)}

    pa_map = {}
    if stocks is not None and not stocks.empty and "prix_achat" in stocks.columns:
        s = stocks[stocks["prix_achat"] > 0]
        pa_map = s.groupby("reference")["prix_achat"].median().to_dict()

    tdf = pd.DataFrame(prev_transfers)
    if tdf.empty or "reference" not in tdf.columns or "destinataire" not in tdf.columns:
        return empty
    tdf["quantite"] = pd.to_numeric(tdf.get("quantite", 0), errors="coerce").fillna(0.0)
    tg = tdf.groupby(["reference", "destinataire"], as_index=False)["quantite"].sum()

    tot_u = tot_ca = tot_m = 0.0
    par: dict = {}
    for r in tg.itertuples(index=False):
        ref, dest, tq = str(r.reference), str(r.destinataire), float(r.quantite)
        su, sca = sold.get((dest, ref), (0.0, 0.0))
        if su <= 0:
            continue
        att = min(su, tq)                       # credit plafonne a ce qu'on a envoye
        pu_ttc = sca / su                       # prix unitaire TTC moyen
        ca_att = att * pu_ttc
        pa = pa_map.get(ref)
        if not pa or pa <= 0:
            pa = pu_ttc / ratio_achat           # repli : achat HT = vente TTC / 2.3
        marge_att = att * (pu_ttc / tva - pa)   # (vente HT - achat HT)
        tot_u += att
        tot_ca += ca_att
        tot_m += marge_att
        d = par.setdefault(dest, {"units": 0.0, "ca": 0.0, "marge": 0.0})
        d["units"] += att
        d["ca"] += ca_att
        d["marge"] += marge_att

    par = {k: {"units": round(x["units"]), "ca": round(x["ca"]), "marge": round(x["marge"])}
           for k, x in par.items()}
    return {"units": round(tot_u), "ca": round(tot_ca),
            "marge": round(tot_m), "par_magasin": par}
