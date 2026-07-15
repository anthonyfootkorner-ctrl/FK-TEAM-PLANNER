"""Genere un run depuis des fichiers deposes dans Supabase Storage.

Lance par l'Action GitHub `stockflow-generate` (declenchee par le relais).
Telecharge les fichiers, fait tourner le moteur, pousse le run dans Supabase,
puis supprime les fichiers temporaires du bucket.

Variables d'environnement :
   SUPABASE_URL, SUPABASE_SERVICE_KEY, BUCKET,
   STOCK_PATH, VENTES_PATH, REASSORT_PATH (opt.), OBJECTIF_PATH (opt.),
   CIBLE (jours, defaut 14)
"""

from __future__ import annotations

import datetime
import io
import json
import os
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402
from stockflow.app_service import build_params, run_analysis  # noqa: E402
from stockflow.impact import compute_impact  # noqa: E402
from stockflow.push_supabase import push  # noqa: E402

URL = os.environ["SUPABASE_URL"].rstrip("/")
KEY = os.environ["SUPABASE_SERVICE_KEY"]
BUCKET = os.environ.get("BUCKET", "stockflow-uploads")


def _dl(path: str | None):
    if not path:
        return None
    r = requests.get(
        f"{URL}/storage/v1/object/{BUCKET}/{path}",
        headers={"apikey": KEY, "Authorization": f"Bearer {KEY}"}, timeout=180,
    )
    r.raise_for_status()
    return io.BytesIO(r.content)


def _rm(path: str | None):
    if not path:
        return
    try:
        requests.delete(
            f"{URL}/storage/v1/object/{BUCKET}/{path}",
            headers={"apikey": KEY, "Authorization": f"Bearer {KEY}"}, timeout=30,
        )
    except Exception:
        pass


def _hdr():
    return {"apikey": KEY, "Authorization": f"Bearer {KEY}"}


def _latest_run():
    r = requests.get(
        f"{URL}/rest/v1/stockflow_runs?select=id,date_execution&order=created_at.desc&limit=1",
        headers=_hdr(), timeout=30)
    d = r.json() if r.status_code == 200 else []
    return d[0] if d else None


def _run_transfers(run_id):
    out, frm = [], 0
    while True:
        r = requests.get(
            f"{URL}/rest/v1/stockflow_transfers?run_id=eq.{run_id}"
            f"&select=reference,destinataire,quantite&limit=1000&offset={frm}",
            headers=_hdr(), timeout=60)
        b = r.json() if r.status_code == 200 else []
        out += b
        if len(b) < 1000:
            break
        frm += 1000
    return out


def _patch_impact(run_id, impact):
    requests.patch(
        f"{URL}/rest/v1/stockflow_runs?id=eq.{run_id}",
        headers={**_hdr(), "Content-Type": "application/json"},
        data=json.dumps({"impact": impact}), timeout=30)


def main() -> int:
    prev = _latest_run()   # dernier run AVANT le nouveau -> pour la mesure d'impact
    stock_p = os.environ.get("STOCK_PATH")
    ventes_p = os.environ.get("VENTES_PATH")
    reassort_p = os.environ.get("REASSORT_PATH") or None
    objectif_p = os.environ.get("OBJECTIF_PATH") or None
    cible = int(os.environ.get("CIBLE", "14"))

    stock = _dl(stock_p)
    ventes = _dl(ventes_p)
    reassort = _dl(reassort_p)
    objectif = _dl(objectif_p)

    today = pd.Timestamp(datetime.date.today())
    result, datasets = run_analysis(
        stock=stock, ventes=ventes, reassort=reassort, objectif=objectif,
        params=build_params(cible=cible), today=today,
    )
    if getattr(result, "blocked", False):
        # on nettoie quand meme puis on echoue clairement
        for p in (stock_p, ventes_p, reassort_p, objectif_p):
            _rm(p)
        raise SystemExit(f"Analyse bloquee : {getattr(result, 'block_reason', 'donnees invalides')}")

    try:
        n_stores = int(datasets["magasins"]["code_magasin"].nunique())
    except Exception:
        n_stores = 0

    meta = {
        "runid": f"web_{today.strftime('%Y%m%d')}_{datetime.datetime.now().strftime('%H%M')}",
        "date_execution": str(today.date()),
        "perimetre": f"{n_stores} magasins" if n_stores else None,
        "cible": cible,
        "parametres": build_params(cible=cible).snapshot(),
    }
    run_id = push(result, meta, url=URL, service_key=KEY)

    # mesure d'impact du run PRECEDENT avec les nouvelles ventes (chez le destinataire)
    if prev and prev.get("id"):
        try:
            imp = compute_impact(_run_transfers(prev["id"]),
                                 datasets.get("ventes_detail"), datasets.get("stocks"),
                                 since_date=prev.get("date_execution"))
            _patch_impact(prev["id"], imp)
            print(f"impact run precedent : {imp.get('units')} articles, "
                  f"CA {imp.get('ca')} €, marge {imp.get('marge')} €")
        except Exception as exc:
            print("impact ignore :", exc)

    for p in (stock_p, ventes_p, reassort_p, objectif_p):
        _rm(p)

    # purge : on ne garde que les N derniers runs (maitrise du stockage / cout).
    # La suppression d'un run efface en cascade ses transferts / revues / expeditions.
    try:
        keep = int(os.environ.get("KEEP_RUNS", "12"))
        r = requests.get(
            f"{URL}/rest/v1/stockflow_runs?select=id&order=created_at.desc",
            headers={"apikey": KEY, "Authorization": f"Bearer {KEY}"}, timeout=30)
        ids = [row["id"] for row in (r.json() or [])]
        for rid in ids[keep:]:
            requests.delete(
                f"{URL}/rest/v1/stockflow_runs?id=eq.{rid}",
                headers={"apikey": KEY, "Authorization": f"Bearer {KEY}"}, timeout=30)
        if len(ids) > keep:
            print(f"purge : {len(ids) - keep} ancien(s) run(s) supprime(s), {keep} conserves")
    except Exception as exc:
        print("purge ignoree :", exc)

    nb = 0 if result.transfers is None else int(len(result.transfers))
    print(f"OK — run {run_id} — {nb} transferts — {meta['perimetre']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
