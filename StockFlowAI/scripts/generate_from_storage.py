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
import shutil
import sys
import tempfile
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402
from stockflow.app_service import build_params, run_analysis  # noqa: E402
from stockflow.impact import compute_impact  # noqa: E402
from stockflow.push_supabase import push, push_reassort_central, push_donors  # noqa: E402
from stockflow.reassort_central import (  # noqa: E402
    build_fastmag_import, build_reassort_excel, build_reassort_email_html)
from stockflow import valorisation as valo  # noqa: E402

REF_DIR = Path(__file__).resolve().parent / "reassort_ref"  # Listing mag + prix de gros

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


def _patch_run(run_id, fields: dict):
    requests.patch(
        f"{URL}/rest/v1/stockflow_runs?id=eq.{run_id}",
        headers={**_hdr(), "Content-Type": "application/json"},
        data=json.dumps(fields), timeout=30)


def _valo_open():
    """Cohortes de valorisation encore ouvertes (plafond non atteint)."""
    out, frm = [], 0
    while True:
        r = requests.get(
            f"{URL}/rest/v1/stockflow_valorisation?closed=eq.false"
            f"&select=id,type,expediteur,destinataire,reference,sent_qty,run_date,"
            f"cumul_units,cumul_ca,cumul_marge,last_date,closed&limit=1000&offset={frm}",
            headers=_hdr(), timeout=60)
        b = r.json() if r.status_code == 200 else []
        out += b
        if len(b) < 1000:
            break
        frm += 1000
    return out


def _valo_patch(rows):
    """Met a jour les cohortes modifiees (une requete par lot d'id)."""
    for row in rows:
        rid = row.get("id")
        if rid is None:
            continue
        body = {k: row[k] for k in ("cumul_units", "cumul_ca", "cumul_marge", "last_date", "closed") if k in row}
        requests.patch(f"{URL}/rest/v1/stockflow_valorisation?id=eq.{rid}",
                       headers={**_hdr(), "Content-Type": "application/json"},
                       data=json.dumps(body), timeout=30)


def _valo_close(ids):
    for i in range(0, len(ids), 100):
        chunk = ids[i:i + 100]
        lst = ",".join(str(x) for x in chunk)
        requests.patch(f"{URL}/rest/v1/stockflow_valorisation?id=in.({lst})",
                       headers={**_hdr(), "Content-Type": "application/json"},
                       data=json.dumps({"closed": True}), timeout=30)


def _valo_insert(rows, chunk=500):
    for i in range(0, len(rows), chunk):
        requests.post(f"{URL}/rest/v1/stockflow_valorisation",
                      headers={**_hdr(), "Content-Type": "application/json", "Prefer": "return=minimal"},
                      data=json.dumps(rows[i:i + chunk]), timeout=60)


def _valo_total_add(delta):
    """Ajoute l'increment valorise de la semaine au total persistant (par piste)."""
    for typ, d in delta.items():
        if not (d["units"] or d["ca"] or d["marge"]):
            continue
        r = requests.get(f"{URL}/rest/v1/stockflow_valo_total?type=eq.{typ}"
                         "&select=units,ca,marge", headers=_hdr(), timeout=30)
        cur = (r.json() or [{}])[0] if r.status_code == 200 and r.json() else {}
        body = {"type": typ,
                "units": int((cur.get("units") or 0) + round(d["units"])),
                "ca": round(float(cur.get("ca") or 0) + d["ca"], 2),
                "marge": round(float(cur.get("marge") or 0) + d["marge"], 2)}
        requests.post(f"{URL}/rest/v1/stockflow_valo_total",
                      headers={**_hdr(), "Content-Type": "application/json",
                               "Prefer": "resolution=merge-duplicates,return=minimal"},
                      data=json.dumps(body), timeout=30)


def _valorisation_step(run_id, run_date, datasets, result):
    """Valorisation cumulative : (1) on accumule les ventes de la semaine sur les
    cohortes ouvertes des runs precedents ; (2) on cree les cohortes de CE run
    (central + inter-magasins), en fermant celles de meme cle. On ajoute aussi
    l'increment de la semaine au total persistant « depuis le debut »."""
    try:
        open_rows = _valo_open()
        upd = valo.accumulate(open_rows, datasets.get("ventes_detail"), datasets.get("stocks"))
        _valo_patch(upd)

        # increment de la semaine -> total persistant (survit a la purge des runs)
        old = {r.get("id"): r for r in open_rows}
        delta = {"central": {"units": 0, "ca": 0.0, "marge": 0.0},
                 "interstore": {"units": 0, "ca": 0.0, "marge": 0.0}}
        for r in upd:
            o = old.get(r.get("id"))
            t = r.get("type")
            if not o or t not in delta:
                continue
            delta[t]["units"] += (r["cumul_units"] - float(o.get("cumul_units", 0)))
            delta[t]["ca"] += (r["cumul_ca"] - float(o.get("cumul_ca", 0)))
            delta[t]["marge"] += (r["cumul_marge"] - float(o.get("cumul_marge", 0)))
        _valo_total_add(delta)

        transfers = []
        t = result.transfers
        if t is not None and not t.empty:
            cols = [c for c in ("expediteur", "destinataire", "reference", "quantite") if c in t.columns]
            transfers = t[cols].to_dict("records")
        new = valo.build_new_cohorts(run_id, run_date, datasets.get("reassort_central"), transfers)
        _valo_close(valo.cohorts_to_close(new, open_rows))
        _valo_insert(new)
        print(f"valorisation : {len(upd)} cohortes maj, {len(new)} nouvelles")
    except Exception as exc:
        print("valorisation ignoree :", exc)


def _upload(path: str, data: bytes, content_type: str = "text/plain"):
    r = requests.post(
        f"{URL}/storage/v1/object/{BUCKET}/{path}",
        headers={**_hdr(), "Content-Type": content_type, "x-upsert": "true"},
        data=data, timeout=120)
    return r.status_code in (200, 201)


def _send_mail(subject, html, attachments):
    """Envoie le mail recap via SMTP (mot de passe d'application Gmail par defaut).

    Secrets attendus (variables d'environnement) : GMAIL_USER + GMAIL_APP_PASSWORD
    (ou SMTP_USER/SMTP_PASS/SMTP_HOST/SMTP_PORT), MAIL_TO (defaut = expediteur).
    Si non configure, on ignore proprement (le fichier reste dispo au telechargement).
    """
    import smtplib
    import ssl
    from email.message import EmailMessage

    user = os.environ.get("GMAIL_USER") or os.environ.get("SMTP_USER")
    pwd = os.environ.get("GMAIL_APP_PASSWORD") or os.environ.get("SMTP_PASS")
    to = os.environ.get("MAIL_TO") or user
    host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    port = int(os.environ.get("SMTP_PORT", "465"))
    if not (user and pwd and to):
        print("e-mail non configure (GMAIL_USER / GMAIL_APP_PASSWORD / MAIL_TO) — envoi ignore")
        return False
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = ", ".join(a.strip() for a in str(to).split(",") if a.strip())
    msg.set_content("Rapport de reassort central en piece jointe (voir la version HTML).")
    msg.add_alternative(html, subtype="html")
    for name, data, ctype in attachments:
        maintype, _, subtype = ctype.partition("/")
        msg.add_attachment(data, maintype=maintype or "application",
                           subtype=subtype or "octet-stream", filename=name)
    ctx = ssl.create_default_context()
    with smtplib.SMTP_SSL(host, port, context=ctx, timeout=60) as s:
        s.login(user, pwd)
        s.send_message(msg)
    print(f"e-mail recap envoye a {msg['To']}")
    return True


def _reassort_central_outputs(run_id, datasets, run_label, central_path):
    """Sortie A (lignes de reassort central en base) + sortie B (import Fastmag
    depose dans le Storage). Ne fait rien si le reassort central n'a pas tourne."""
    rc = datasets.get("reassort_central")
    if rc is None or rc.empty:
        return
    try:
        n = push_reassort_central(run_id, rc, url=URL, service_key=KEY)
        print(f"reassort central : {n} lignes (sortie A)")
    except Exception as exc:
        print("reassort central (A) ignore :", exc)

    # Sortie B : fichier d'import Fastmag. On prepare un dossier de reference
    # (Listing mag + prix de gros versionnes) + le stock CENTRAL (couleurs).
    try:
        with tempfile.TemporaryDirectory() as tmp:
            tmpd = Path(tmp)
            if REF_DIR.exists():
                for f in REF_DIR.iterdir():
                    if f.is_file():
                        shutil.copy2(f, tmpd / f.name)
            # le stock CENTRAL sert de source couleur (central_couleur)
            cdata = _dl(central_path)
            if cdata is not None:
                (tmpd / "stock_central.xls").write_bytes(cdata.getvalue())
            out = tmpd / "IMPORT_FASTMAG.txt"
            nb, nbb, sans = build_fastmag_import(rc, out, tmpd,
                                                 run_date=datetime.datetime.now())
            fastmag_bytes = None
            if nb > 0:
                fastmag_bytes = out.read_bytes()
                dest = f"exports/{run_label}/IMPORT_FASTMAG.txt"
                if _upload(dest, fastmag_bytes, "text/plain; charset=latin1"):
                    _patch_run(run_id, {"fastmag_import": dest})
                    print(f"import Fastmag : {nb} lignes -> {dest} (sortie B)")
                if sans:
                    print("boutiques sans numero Fastmag :", ", ".join(sans))

            # Classeur Excel recap (comme l'outil historique) + e-mail
            res = datasets.get("reassort_central_result")
            xlsx_bytes = None
            _XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            try:
                xlsx_path = tmpd / f"reassort_{run_label}.xlsx"
                if build_reassort_excel(res, xlsx_path):
                    xlsx_bytes = xlsx_path.read_bytes()
                    dx = f"exports/{run_label}/reassort.xlsx"
                    if _upload(dx, xlsx_bytes, _XLSX):
                        _patch_run(run_id, {"reassort_excel": dx})
                        print(f"classeur Excel : {dx}")
            except Exception as exc:
                print("classeur Excel ignore :", exc)

            try:
                html = build_reassort_email_html(res, run_date=datetime.datetime.now())
                if html:
                    atts = []
                    if xlsx_bytes:
                        atts.append((f"reassort_{run_label}.xlsx", xlsx_bytes, _XLSX))
                    if fastmag_bytes:
                        atts.append(("IMPORT_FASTMAG.txt", fastmag_bytes, "text/plain"))
                    _send_mail(f"Reassort central — {run_label}", html, atts)
            except Exception as exc:
                print("e-mail recap ignore :", exc)
    except Exception as exc:
        print("sorties reassort (B/Excel/mail) ignorees :", exc)


def main() -> int:
    prev = _latest_run()   # dernier run AVANT le nouveau -> pour la mesure d'impact
    stock_p = os.environ.get("STOCK_PATH")
    ventes_p = os.environ.get("VENTES_PATH")
    reassort_p = os.environ.get("REASSORT_PATH") or None
    objectif_p = os.environ.get("OBJECTIF_PATH") or None
    central_p = os.environ.get("CENTRAL_PATH") or None
    cible = int(os.environ.get("CIBLE", "21"))

    stock = _dl(stock_p)
    ventes = _dl(ventes_p)
    reassort = _dl(reassort_p)
    objectif = _dl(objectif_p)
    central = _dl(central_p)

    today = pd.Timestamp(datetime.date.today())
    result, datasets = run_analysis(
        stock=stock, ventes=ventes, reassort=reassort, objectif=objectif,
        central_stock=central, params=build_params(cible=cible), today=today,
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

    # reassort central : sortie A (base) + sortie B (import Fastmag dans Storage)
    _reassort_central_outputs(run_id, datasets, meta["runid"], central_p)

    # valorisation cumulative (central + inter-magasins, credit expediteur)
    _valorisation_step(run_id, today, datasets, result)

    # donneurs (surplus) : proposition de depannage sur les demandes urgentes
    try:
        nd = push_donors(run_id, getattr(result, "donors", None), url=URL, service_key=KEY)
        print(f"donneurs : {nd} lignes (depannage demandes urgentes)")
    except Exception as exc:
        print("donneurs ignores :", exc)

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

    for p in (stock_p, ventes_p, reassort_p, objectif_p, central_p):
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
