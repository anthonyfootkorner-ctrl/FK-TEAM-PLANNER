"""Backend StockFlow.AI — RELAIS leger (upload -> Supabase Storage -> Action GitHub).

Le moteur (pandas) est trop gourmand pour un hebergement gratuit (512 Mo).
Ce service ne fait donc PAS le calcul : il se contente de
 1) verifier que l'appelant est bien l'admin (jeton Supabase) ;
 2) deposer les fichiers dans un bucket prive Supabase Storage ;
 3) declencher l'Action GitHub `stockflow-generate` qui, elle, fait tourner
    le moteur sur les serveurs GitHub (7 Go) et pousse le run dans Supabase.

Aucune dependance lourde -> tient largement dans 512 Mo.

Variables d'environnement (cote serveur uniquement) :
   SUPABASE_URL           https://xxxx.supabase.co
   SUPABASE_SERVICE_KEY   cle secrete Supabase (sb_secret_...)
   SUPABASE_ANON_KEY      cle publishable (verification des jetons)
   GH_TOKEN               jeton GitHub (droit d'ecriture sur le depot)
   GH_REPO                owner/repo, ex. anthonyfootkorner-ctrl/FK-TEAM-PLANNER
   BUCKET                 (optionnel) nom du bucket, defaut "stockflow-uploads"
"""

from __future__ import annotations

import datetime
import json
import os

import requests
from fastapi import Body, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")
GH_TOKEN = os.environ.get("GH_TOKEN", "")
GH_REPO = os.environ.get("GH_REPO", "")
BUCKET = os.environ.get("BUCKET", "stockflow-uploads")

app = FastAPI(title="StockFlow.AI relay")
# CORS ouvert : la securite vient du jeton admin, pas de CORS.
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def _svc():
    return {"apikey": SERVICE_KEY, "Authorization": f"Bearer {SERVICE_KEY}"}


def _verify_admin(token: str) -> str:
    if not token:
        raise HTTPException(401, "Non authentifie (jeton manquant).")
    if not (SUPABASE_URL and SERVICE_KEY):
        raise HTTPException(500, "Backend mal configure (SUPABASE_URL / SUPABASE_SERVICE_KEY).")
    r = requests.get(
        f"{SUPABASE_URL}/auth/v1/user",
        headers={"apikey": ANON_KEY or SERVICE_KEY, "Authorization": f"Bearer {token}"},
        timeout=15,
    )
    if r.status_code != 200:
        raise HTTPException(401, "Session invalide ou expiree.")
    uid = r.json().get("id")
    rr = requests.get(
        f"{SUPABASE_URL}/rest/v1/stockflow_user_stores",
        params={"user_id": f"eq.{uid}", "select": "magasin"},
        headers=_svc(), timeout=15,
    )
    if rr.status_code == 200 and rr.json():
        raise HTTPException(403, "Reserve a l'administrateur.")
    return uid


def _ensure_bucket():
    # cree le bucket prive s'il n'existe pas (idempotent ; ignore l'erreur "existe deja")
    requests.post(
        f"{SUPABASE_URL}/storage/v1/bucket",
        headers={**_svc(), "Content-Type": "application/json"},
        json={"name": BUCKET, "public": False}, timeout=15,
    )


def _upload(path: str, data: bytes, content_type: str | None):
    r = requests.post(
        f"{SUPABASE_URL}/storage/v1/object/{BUCKET}/{path}",
        headers={**_svc(), "Content-Type": content_type or "application/octet-stream", "x-upsert": "true"},
        data=data, timeout=120,
    )
    if r.status_code not in (200, 201):
        raise HTTPException(502, f"Depot du fichier echoue ({r.status_code}) : {r.text[:200]}")


def _set_stores(uid: str, stores):
    """Remplace l'affectation magasins d'un utilisateur."""
    requests.delete(f"{SUPABASE_URL}/rest/v1/stockflow_user_stores",
                    params={"user_id": f"eq.{uid}"}, headers=_svc(), timeout=15)
    rows = [{"user_id": uid, "magasin": str(s).strip()} for s in (stores or []) if str(s).strip()]
    if rows:
        r = requests.post(f"{SUPABASE_URL}/rest/v1/stockflow_user_stores",
                          headers={**_svc(), "Content-Type": "application/json"},
                          data=json.dumps(rows), timeout=15)
        if r.status_code not in (200, 201):
            raise HTTPException(502, f"Affectation magasins echouee ({r.status_code}) : {r.text[:200]}")


@app.get("/users")
def list_users(authorization: str | None = Header(None)):
    _verify_admin((authorization or "").replace("Bearer ", "").strip())
    r = requests.get(f"{SUPABASE_URL}/auth/v1/admin/users",
                     params={"per_page": 200}, headers=_svc(), timeout=20)
    users = (r.json() or {}).get("users", []) if r.status_code == 200 else []
    m = requests.get(f"{SUPABASE_URL}/rest/v1/stockflow_user_stores",
                     params={"select": "user_id,magasin"}, headers=_svc(), timeout=15)
    by_user: dict = {}
    for row in (m.json() or []) if m.status_code == 200 else []:
        by_user.setdefault(row["user_id"], []).append(row["magasin"])
    out = [{"id": u["id"], "email": u.get("email"),
            "stores": sorted(by_user.get(u["id"], [])),
            "created_at": u.get("created_at")} for u in users]
    out.sort(key=lambda x: (0 if not x["stores"] else 1, x["email"] or ""))
    return {"users": out}


@app.post("/users")
def create_user(payload: dict = Body(...), authorization: str | None = Header(None)):
    _verify_admin((authorization or "").replace("Bearer ", "").strip())
    email = (payload.get("email") or "").strip()
    password = payload.get("password") or ""
    stores = payload.get("stores") or []
    if not email or len(password) < 6:
        raise HTTPException(400, "E-mail requis et mot de passe d'au moins 6 caracteres.")
    r = requests.post(f"{SUPABASE_URL}/auth/v1/admin/users",
                      headers={**_svc(), "Content-Type": "application/json"},
                      data=json.dumps(
                          {"email": email, "password": password, "email_confirm": True}),
                      timeout=20)
    if r.status_code not in (200, 201):
        raise HTTPException(400, f"Creation impossible : {r.text[:200]}")
    uid = r.json().get("id")
    _set_stores(uid, stores)
    return {"id": uid, "email": email, "stores": stores}


@app.post("/users/{uid}/stores")
def update_stores(uid: str, payload: dict = Body(...), authorization: str | None = Header(None)):
    _verify_admin((authorization or "").replace("Bearer ", "").strip())
    _set_stores(uid, payload.get("stores") or [])
    return {"ok": True}


@app.delete("/users/{uid}")
def delete_user(uid: str, authorization: str | None = Header(None)):
    _verify_admin((authorization or "").replace("Bearer ", "").strip())
    requests.delete(f"{SUPABASE_URL}/rest/v1/stockflow_user_stores",
                    params={"user_id": f"eq.{uid}"}, headers=_svc(), timeout=15)
    r = requests.delete(f"{SUPABASE_URL}/auth/v1/admin/users/{uid}", headers=_svc(), timeout=20)
    if r.status_code not in (200, 204):
        raise HTTPException(400, f"Suppression impossible : {r.text[:200]}")
    return {"ok": True}


@app.get("/health")
def health():
    return {"ok": True, "configured": bool(SUPABASE_URL and SERVICE_KEY and GH_TOKEN and GH_REPO)}


@app.get("/")
def root():
    return {"service": "stockflow-relay", "endpoints": ["/health", "/generer"]}


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
    if not (GH_TOKEN and GH_REPO):
        raise HTTPException(500, "Backend mal configure (GH_TOKEN / GH_REPO).")

    _ensure_bucket()
    prefix = "runs/" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    payload = {"cible": int(cible), "bucket": BUCKET,
               "reassort": None, "objectif": None}

    _upload(f"{prefix}/stock", await stock.read(), stock.content_type)
    payload["stock"] = f"{prefix}/stock"
    _upload(f"{prefix}/ventes", await ventes.read(), ventes.content_type)
    payload["ventes"] = f"{prefix}/ventes"
    if reassort is not None:
        _upload(f"{prefix}/reassort", await reassort.read(), reassort.content_type)
        payload["reassort"] = f"{prefix}/reassort"
    if objectif is not None:
        _upload(f"{prefix}/objectif", await objectif.read(), objectif.content_type)
        payload["objectif"] = f"{prefix}/objectif"

    gh = requests.post(
        f"https://api.github.com/repos/{GH_REPO}/dispatches",
        headers={"Authorization": f"Bearer {GH_TOKEN}", "Accept": "application/vnd.github+json"},
        json={"event_type": "stockflow-generate", "client_payload": payload}, timeout=20,
    )
    if gh.status_code != 204:
        raise HTTPException(502, f"Declenchement GitHub echoue ({gh.status_code}) : {gh.text[:200]}")

    return {"status": "lance", "cible": int(cible)}
