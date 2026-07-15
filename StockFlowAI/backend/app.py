"""Backend StockFlow.AI — genere les transferts depuis des fichiers uploades.

Recoit les exports Fastmag (stock + ventes, + reassort/objectif optionnels),
lance le moteur, et pousse le run dans Supabase. Concu pour un hebergement
gratuit (Render / Railway / Fly).

Securite :
 - l'appelant doit fournir le jeton de session Supabase (Authorization: Bearer),
   qui est verifie aupres de Supabase ;
 - seul un compte ADMIN (non rattache a un magasin) peut generer.

Variables d'environnement requises (cote serveur, jamais dans le navigateur) :
   SUPABASE_URL           https://xxxx.supabase.co
   SUPABASE_SERVICE_KEY   cle secrete (service_role / sb_secret_...)
   SUPABASE_ANON_KEY      cle publishable (pour verifier les jetons)
   ALLOW_ORIGINS          origines autorisees (CORS), ex. https://xxx.netlify.app
"""

from __future__ import annotations

import datetime
import io
import os
import sys

# rend le paquet `stockflow` importable quel que soit le repertoire de lancement
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd  # noqa: E402
import requests  # noqa: E402
from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

from stockflow.app_service import build_params, run_analysis  # noqa: E402
from stockflow.push_supabase import push  # noqa: E402

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")
ALLOW_ORIGINS = [o.strip() for o in os.environ.get("ALLOW_ORIGINS", "*").split(",") if o.strip()]

app = FastAPI(title="StockFlow.AI backend")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOW_ORIGINS or ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _verify_admin(access_token: str) -> str:
    """Verifie le jeton Supabase et exige un compte admin (sans magasin)."""
    if not access_token:
        raise HTTPException(401, "Non authentifie (jeton manquant).")
    if not SUPABASE_URL or not SERVICE_KEY:
        raise HTTPException(500, "Backend mal configure (SUPABASE_URL / SUPABASE_SERVICE_KEY).")
    # 1) le jeton correspond-il a un utilisateur valide ?
    r = requests.get(
        f"{SUPABASE_URL}/auth/v1/user",
        headers={"apikey": ANON_KEY or SERVICE_KEY, "Authorization": f"Bearer {access_token}"},
        timeout=15,
    )
    if r.status_code != 200:
        raise HTTPException(401, "Session invalide ou expiree.")
    uid = r.json().get("id")
    # 2) admin = non rattache a un magasin
    rr = requests.get(
        f"{SUPABASE_URL}/rest/v1/stockflow_user_stores",
        params={"user_id": f"eq.{uid}", "select": "magasin"},
        headers={"apikey": SERVICE_KEY, "Authorization": f"Bearer {SERVICE_KEY}"},
        timeout=15,
    )
    if rr.status_code == 200 and rr.json():
        raise HTTPException(403, "Reserve a l'administrateur.")
    return uid


@app.get("/health")
def health():
    return {"ok": True, "configured": bool(SUPABASE_URL and SERVICE_KEY)}


@app.post("/generer")
async def generer(
    stock: UploadFile = File(...),
    ventes: UploadFile = File(...),
    reassort: UploadFile | None = File(None),
    objectif: UploadFile | None = File(None),
    cible: int = Form(14),
    authorization: str | None = Header(None),
):
    token = (authorization or "").replace("Bearer ", "").strip()
    _verify_admin(token)

    stock_b = io.BytesIO(await stock.read())
    ventes_b = io.BytesIO(await ventes.read())
    reassort_b = io.BytesIO(await reassort.read()) if reassort is not None else None
    objectif_b = io.BytesIO(await objectif.read()) if objectif is not None else None

    params = build_params(cible=int(cible))
    today = pd.Timestamp(datetime.date.today())

    try:
        result, datasets = run_analysis(
            stock=stock_b, ventes=ventes_b, reassort=reassort_b, objectif=objectif_b,
            params=params, today=today,
        )
    except Exception as exc:  # erreurs de lecture / format
        raise HTTPException(400, f"Lecture des fichiers impossible : {exc}")

    if getattr(result, "blocked", False):
        raise HTTPException(422, f"Analyse bloquee : {getattr(result, 'block_reason', 'donnees invalides')}")

    try:
        n_stores = int(datasets["magasins"]["code_magasin"].nunique())
    except Exception:
        n_stores = 0

    now = datetime.datetime.now()
    meta = {
        "runid": f"web_{now.strftime('%Y%m%d_%H%M')}",
        "date_execution": str(today.date()),
        "perimetre": f"{n_stores} magasins" if n_stores else None,
        "cible": int(cible),
        "parametres": params.snapshot(),
    }

    run_id = push(result, meta, url=SUPABASE_URL, service_key=SERVICE_KEY)
    nb = 0 if result.transfers is None else int(len(result.transfers))
    return {"run_id": run_id, "nb_transferts": nb, "perimetre": meta["perimetre"], "cible": int(cible)}
