# STOCKFLOW.AI — interface web

Deux etapes : un **prototype** cliquable (validation ergonomie), puis la
**version hebergee** sur Supabase (multi-utilisateurs, revue partagee).

## 1. Prototype (déjà disponible)

```bash
python webapp/build_prototype.py
```

Genere `webapp/stockflow_prototype.html` (autonome, a ouvrir dans un navigateur)
a partir du dernier export Excel + fiche de revue. Onglets, vue par magasin,
revue OK/NON (memoire du navigateur), export CSV. Identite : thème sombre,
titres Montserrat ExtraBold (`webapp/display.woff2`, embarquee en data-URI car
la CSP interdit les CDN).

## 2. Version hebergee (Supabase)

Reutilise la stack du FK Team Planner (Supabase Auth + Postgres + frontend
statique).

```
Moteur Python (hebdo) ──push──▶ Supabase (Postgres + Auth) ◀──lit/écrit── Frontend statique
   run_real --push              stockflow_runs/transfers/reviews    onglets · vue magasin · revue OK/NON
```

### Étape A — créer les tables
Dans Supabase > **SQL Editor**, executer `webapp/supabase_schema.sql`
(idempotent). Cree `stockflow_runs`, `stockflow_transfers`, `stockflow_reviews`
+ RLS : lecture pour les utilisateurs connectes, chacun gere ses propres revues.

### Étape B — pousser un run
```bash
export SUPABASE_URL="https://xxxx.supabase.co"
export SUPABASE_SERVICE_KEY="<cle service_role>"   # SECRET, jamais dans le frontend
python run_real.py --stock ... --ventes ... --reassort ... --push
```
Verification sans envoi :
```bash
python run_real.py ... --push-dry-run   # ecrit exports/supabase_payload.json
```
La cle `service_role` contourne les RLS pour l'insertion ; elle reste **cote
serveur** (script d'execution / cron hebdomadaire), jamais dans la page web.

### Étape C — frontend hebergé (a venir)
Le prototype sera branche sur Supabase : lecture des transferts via
`supabase-js` (clé publishable + auth), revue OK/NON ecrite dans
`stockflow_reviews` (partagee entre utilisateurs). Meme UI, meme identite.

## Fichiers

| Fichier | Role |
|---|---|
| `build_prototype.py` | genere le prototype autonome |
| `display.woff2` | Montserrat ExtraBold (titres), OFL |
| `supabase_schema.sql` | schema + RLS des tables StockFlow |
| `../stockflow/push_supabase.py` | push des resultats vers Supabase |

> Les `.html`/`.png` generes ne sont pas versionnes (regenerables).
