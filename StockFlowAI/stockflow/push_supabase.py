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
        for i, r in t.iterrows():
            ref = str(r.get("reference", ""))
            transfers.append({
                "n": i + 1,
                "priorite": r.get("priorite"),
                "score": _num(r.get("score")),
                "marque": marque_map.get((ref, str(r.get("couleur", ""))), r.get("marque", "")),
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
