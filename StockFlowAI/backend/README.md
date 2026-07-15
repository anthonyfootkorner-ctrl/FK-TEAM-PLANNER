# Backend StockFlow.AI (bouton « Générer »)

Petit service qui reçoit les fichiers Fastmag, lance le moteur et pousse le
run dans Supabase. À héberger gratuitement (Render conseillé).

## Ce qu'il expose
- `GET /health` — vérifie que le service tourne.
- `POST /generer` — multipart : `stock`, `ventes` (obligatoires), `reassort`,
  `objectif` (optionnels), `cible` (jours). En-tête `Authorization: Bearer <jeton Supabase>`.
  Seul un compte **admin** (non rattaché à un magasin) est autorisé.

## Déployer sur Render (gratuit)
1. Va sur https://render.com → **New +** → **Web Service** → connecte le dépôt GitHub.
2. **Root Directory** : `StockFlowAI`
3. **Runtime** : Python 3
4. **Build Command** : `pip install -r backend/requirements.txt`
5. **Start Command** : `uvicorn backend.app:app --host 0.0.0.0 --port $PORT`
6. **Environment Variables** (onglet Environment) :
   - `SUPABASE_URL` = `https://yeusqubxgxchigssobma.supabase.co`
   - `SUPABASE_SERVICE_KEY` = ta clé **secrète** Supabase (`sb_secret_...`) — jamais ailleurs.
   - `SUPABASE_ANON_KEY` = ta clé **publishable** (`sb_publishable_...`).
   - `ALLOW_ORIGINS` = l'URL de ton site Netlify, ex. `https://cheery-rugelach-69211c.netlify.app`
7. **Create Web Service**. Une fois « Live », copie l'URL (ex. `https://stockflow-xxxx.onrender.com`)
   et donne-la moi : je la mets dans le site (`BACKEND_URL`).

Note : sur le plan gratuit, le service s'endort après ~15 min d'inactivité ;
la 1re génération de la journée peut donc prendre ~30 s de plus (réveil).

## Tester en local (optionnel)
```
cd StockFlowAI
pip install -r backend/requirements.txt
SUPABASE_URL=... SUPABASE_SERVICE_KEY=... SUPABASE_ANON_KEY=... \
  uvicorn backend.app:app --reload
# puis http://127.0.0.1:8000/health
```
