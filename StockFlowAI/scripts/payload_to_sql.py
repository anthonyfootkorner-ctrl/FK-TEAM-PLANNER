"""Convertit le payload JSON en script SQL INSERT (a coller dans Supabase).

Permet d'inserer un run + ses transferts SANS cle ni reseau : on colle le SQL
dans Supabase > SQL Editor (qui a les droits admin). Idéal pour un premier test.

Usage :
    python scripts/payload_to_sql.py webapp/supabase_payload.json out.sql [--run-id UUID]
"""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

TCOLS = ["n", "priorite", "score", "marque", "expediteur", "destinataire",
         "reference", "taille", "quantite", "cov_dest_avant", "cov_dest_apres",
         "grille_avant", "grille_apres", "dispo_finale", "picking_prevu", "motif"]
NUMERIC = {"n", "score", "quantite", "cov_dest_avant", "cov_dest_apres", "picking_prevu"}


def q(v) -> str:
    """Litteral SQL : NULL, nombre, ou chaine echappee."""
    if v is None:
        return "NULL"
    if isinstance(v, (int, float)):
        return repr(v)
    return "'" + str(v).replace("'", "''") + "'"


def qnum(v) -> str:
    if v is None or v == "":
        return "NULL"
    try:
        f = float(v)
        return repr(int(f) if f.is_integer() else f)
    except (TypeError, ValueError):
        return "NULL"


def main() -> int:
    payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    out = Path(sys.argv[2])
    run_id = sys.argv[4] if len(sys.argv) > 4 and sys.argv[3] == "--run-id" else str(uuid.uuid4())

    run = payload["run"]
    transfers = payload["transfers"]
    for i, a in enumerate(sys.argv):
        if a == "--limit" and i + 1 < len(sys.argv):
            transfers = transfers[:int(sys.argv[i + 1])]
    kpis = json.dumps(run.get("kpis", {}), ensure_ascii=False)

    # nombre de fichiers (par defaut 3) ; le run est insere dans la partie 1
    nparts = 3
    for i, a in enumerate(sys.argv):
        if a == "--parts" and i + 1 < len(sys.argv):
            nparts = int(sys.argv[i + 1])

    run_insert = (
        "insert into public.stockflow_runs "
        "(id, label, date_execution, perimetre, cible, nb_transferts, kpis) values ("
        f"{q(run_id)}, {q(run.get('label'))}, {q(run.get('date_execution'))}, "
        f"{q(run.get('perimetre'))}, {qnum(run.get('cible'))}, {qnum(run.get('nb_transferts'))}, "
        f"{q(kpis)}::jsonb);"
    )
    cols = "run_id, " + ", ".join(TCOLS)

    def row_sql(t):
        vals = [q(run_id)]
        for c in TCOLS:
            vals.append(qnum(t.get(c)) if c in NUMERIC else q(t.get(c)))
        return "(" + ", ".join(vals) + ")"

    per = -(-len(transfers) // nparts)  # ceil
    written = []
    for part in range(nparts):
        seg = transfers[part * per:(part + 1) * per]
        if not seg and part > 0:
            continue
        L = [f"-- STOCKFLOW.AI — insertion (partie {part+1}/{nparts}) — run_id {run_id}"]
        if part == 0:
            L.append("-- Partie 1 : cree le run PUIS ses premiers transferts.")
            L.append(run_insert)
        # inserts par lots de 500 pour rester raisonnable
        for i in range(0, len(seg), 500):
            batch = seg[i:i + 500]
            L.append(f"insert into public.stockflow_transfers ({cols}) values")
            L.append(",\n".join(row_sql(t) for t in batch) + ";")
        p = out.with_name(out.stem + f"_partie{part+1}.sql")
        p.write_text("\n".join(L), encoding="utf-8")
        written.append(p)
        print(f"  {p.name} : {p.stat().st_size/1024:.0f} Ko, {len(seg)} transferts")
    print(f"OK — {len(written)} fichiers, run_id {run_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
