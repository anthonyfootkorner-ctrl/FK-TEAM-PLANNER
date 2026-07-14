"""Pousse un payload JSON (run + transfers) vers Supabase.

Usage :
    SUPABASE_URL=...  SUPABASE_SERVICE_KEY=...  \
        python scripts/push_payload.py webapp/supabase_payload.json

Concu pour tourner dans une GitHub Action : la cle secrete provient d'un
GitHub Secret (jamais du code). Ne depend que de `requests`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from stockflow.push_supabase import push_payload  # noqa: E402


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: python scripts/push_payload.py <payload.json>", file=sys.stderr)
        return 2
    payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    run_id = push_payload(payload["run"], payload["transfers"])
    print(f"OK — run insere : {run_id} ({len(payload['transfers'])} transferts)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
