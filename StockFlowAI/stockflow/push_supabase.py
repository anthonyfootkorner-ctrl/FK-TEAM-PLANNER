"""Pousse les resultats du moteur vers Supabase (tables stockflow_*).

Le moteur pandas ne tourne pas dans Supabase : il pousse ses resultats via
l'API REST (PostgREST) apres chaque run. Le frontend hebergé lit ensuite ces
tables (avec auth) et gere la revue OK/NON partagee.

Identifiants (variables d'environnement) :
    SUPABASE_URL            ex. https://xxxx.supabase.co
    SUPABASE_SERVICE_KEY    cle service_role (contourne RLS pour l'insertion)

La cle service_role est SECRETE : ne jamais la mettre dans le frontend ni la
versionner. Utiliser uniquement cote serveur / script d'execution.
"""

from __future__ import annotations

import json
import os
from typing import Dict, List, Optional, Tuple

# NB : pandas n'est importe que par build_payload/dry_run (cote moteur). Le
# chemin "pousser un payload JSON deja calcule" (GitHub Action) ne depend que
# de `requests`, pour rester leger.


def build_payload(result, meta: Dict) -> Tuple[Dict, List[Dict]]:
    """Construit (run, transfers[]) prets a etre inseres. Testable hors ligne."""
    sim = result.simulation_global
    kpis = {}
    if sim is not None and not sim.empty:
        kpis = {str(r["indicateur"]): {"avant": _num(r["avant"]), "apres": _num(r["apres"])}
                for _, r in sim.iterrows()}

    run = {
        "label": meta.get("runid") or meta.get("label"),
        "date_execution": meta.get("date_execution") or str(meta.get("date", "")) or None,
        "perimetre": meta.get("perimetre"),
        "cible": meta.get("cible"),
        "nb_transferts": 0 if result.transfers is None else int(len(result.transfers)),
        "kpis": kpis,
        "parametres": meta.get("parametres", {}),
    }

    transfers: List[Dict] = []
    t = result.transfers
    if t is not None and not t.empty:
        t = t.sort_values("score", ascending=False).reset_index(drop=True)
        marque_map = meta.get("marque_map", {})
        desig_map = meta.get("designation_map", {}) or {}
        for i, r in t.iterrows():
            ref = str(r.get("reference", ""))
            transfers.append({
                "n": i + 1,
                "priorite": r.get("priorite"),
                "score": _num(r.get("score")),
                "marque": marque_map.get((ref, str(r.get("couleur", ""))), r.get("marque", "")),
                "designation": desig_map.get(ref) or None,
                "expediteur": r.get("expediteur"),
                "destinataire": r.get("destinataire"),
                "reference": ref,
                "taille": str(r.get("taille", "")),
                "quantite": _num(r.get("quantite")),
                "cov_dest_avant": _num(r.get("cov_dest_avant")),
                "cov_dest_apres": _num(r.get("cov_dest_apres")),
                "grille_avant": r.get("grille_avant"),
                "grille_apres": r.get("grille_apres"),
                "dispo_finale": r.get("dispo_finale_dest", ""),
                "picking_prevu": _num(r.get("picking_prevu")),
                "motif": r.get("motif"),
            })
    return run, transfers


def push_payload(run: Dict, transfers: List[Dict], *, url: Optional[str] = None,
                 service_key: Optional[str] = None, chunk: int = 500) -> str:
    """Insere un run + ses transferts (deja construits). Renvoie l'id du run."""
    import requests

    url = (url or os.environ.get("SUPABASE_URL", "")).rstrip("/")
    service_key = service_key or os.environ.get("SUPABASE_SERVICE_KEY", "")
    if not url or not service_key:
        raise RuntimeError("SUPABASE_URL et SUPABASE_SERVICE_KEY requis "
                           "(variables d'environnement ou arguments).")
    base = f"{url}/rest/v1"
    headers = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }
    resp = requests.post(f"{base}/stockflow_runs", headers=headers,
                         data=json.dumps(run), timeout=30)
    resp.raise_for_status()
    run_id = resp.json()[0]["id"]
    for i in range(0, len(transfers), chunk):
        batch = [{**row, "run_id": run_id} for row in transfers[i:i + chunk]]
        r = requests.post(f"{base}/stockflow_transfers",
                          headers={**headers, "Prefer": "return=minimal"},
                          data=json.dumps(batch), timeout=60)
        r.raise_for_status()
    return run_id


def push(result, meta: Dict, *, url: Optional[str] = None, service_key: Optional[str] = None,
         chunk: int = 500) -> str:
    """Insere le run puis ses transferts dans Supabase. Renvoie l'id du run."""
    run, transfers = build_payload(result, meta)
    return push_payload(run, transfers, url=url, service_key=service_key, chunk=chunk)


def build_reassort_rows(proposed) -> List[Dict]:
    """Serialise la sortie du reassort central (sortie A) en lignes compactes."""
    rows: List[Dict] = []
    if proposed is None or getattr(proposed, "empty", True):
        return rows
    for r in proposed.itertuples(index=False):
        qte = _num(getattr(r, "qte_proposee", 0))
        if not qte or qte <= 0:
            continue
        rows.append({
            "boutique": str(getattr(r, "boutique", "")),
            "reference": str(getattr(r, "barcode", "")),
            "taille": str(getattr(r, "taille", "")),
            "marque": (str(getattr(r, "marque", "")) or None),
            "qte": int(qte),
            "priorite": getattr(r, "priorite", None),
            "commentaire": getattr(r, "commentaire", None),
            "couverture_j": _num(getattr(r, "couverture_jours", None)),
            "besoin": _num(getattr(r, "besoin_theorique", None)),
            "stock": _num(getattr(r, "stock", None)),
            "tailles_apres": getattr(r, "tailles_stock_boutique", None),
        })
    return rows


def push_reassort_central(run_id: str, proposed, *, url: Optional[str] = None,
                          service_key: Optional[str] = None, chunk: int = 500) -> int:
    """Insere les lignes de reassort central pour un run. Renvoie le nb insere."""
    import requests

    rows = build_reassort_rows(proposed)
    if not rows:
        return 0
    url = (url or os.environ.get("SUPABASE_URL", "")).rstrip("/")
    service_key = service_key or os.environ.get("SUPABASE_SERVICE_KEY", "")
    base = f"{url}/rest/v1"
    headers = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }
    for i in range(0, len(rows), chunk):
        batch = [{**row, "run_id": run_id} for row in rows[i:i + chunk]]
        r = requests.post(f"{base}/stockflow_reassort_central",
                          headers=headers, data=json.dumps(batch), timeout=60)
        r.raise_for_status()
    return len(rows)


def build_donor_rows(donors) -> List[Dict]:
    """Serialise les donneurs (surplus mobilisable) pour la proposition de
    depannage sur une demande urgente. Une ligne par (magasin, reference, taille)."""
    rows: List[Dict] = []
    if donors is None or getattr(donors, "empty", True):
        return rows
    for r in donors.itertuples(index=False):
        qte = _num(getattr(r, "qte_don_max", 0))
        if not qte or qte <= 0:
            continue
        cov = _num(getattr(r, "couverture_projetee", None))
        if cov is not None and cov > 999:
            cov = 999
        rows.append({
            "magasin": str(getattr(r, "magasin", "")),
            "reference": str(getattr(r, "reference", "")),
            "taille": str(getattr(r, "taille", "")),
            "qte_don": int(qte),
            "couverture_j": cov,
            "ventes_jour": _num(getattr(r, "moyenne_quotidienne", None)),
            "motif": getattr(r, "motif_donneur", None),
        })
    return rows


def push_donors(run_id: str, donors, *, url: Optional[str] = None,
                service_key: Optional[str] = None, chunk: int = 500) -> int:
    """Insere les donneurs d'un run puis purge ceux des autres runs (on ne garde
    que la photo courante : une demande urgente concerne le stock d'aujourd'hui)."""
    import requests

    rows = build_donor_rows(donors)
    url = (url or os.environ.get("SUPABASE_URL", "")).rstrip("/")
    service_key = service_key or os.environ.get("SUPABASE_SERVICE_KEY", "")
    base = f"{url}/rest/v1"
    headers = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }
    for i in range(0, len(rows), chunk):
        batch = [{**row, "run_id": run_id} for row in rows[i:i + chunk]]
        r = requests.post(f"{base}/stockflow_donors", headers=headers,
                          data=json.dumps(batch), timeout=60)
        r.raise_for_status()
    # purge des donneurs des autres runs (on ne garde que le run courant)
    try:
        requests.delete(f"{base}/stockflow_donors?run_id=neq.{run_id}",
                        headers=headers, timeout=30)
    except Exception:
        pass
    return len(rows)


def dry_run(result, meta: Dict, out_path) -> Dict:
    """Ecrit le payload dans un JSON (sans Supabase) pour verification."""
    run, transfers = build_payload(result, meta)
    payload = {"run": run, "transfers": transfers}
    from pathlib import Path
    Path(out_path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"run": run, "nb_transferts": len(transfers)}


def _num(v):
    # NaN vaut != a lui-meme : evite d'importer pandas juste pour isna().
    if v is None or (isinstance(v, float) and v != v):
        return None
    try:
        f = float(v)
        return int(f) if f.is_integer() else round(f, 2)
    except (TypeError, ValueError):
        return v
