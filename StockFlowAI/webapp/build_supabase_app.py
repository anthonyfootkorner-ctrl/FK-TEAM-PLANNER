"""Genere l'appli web hebergee (connectee a Supabase).

Reutilise le CSS, le markup et TOUTE la logique de rendu du prototype
(build_prototype.HTML_TEMPLATE) et ne remplace que :
  * la source des donnees  -> Supabase (tables stockflow_*) ;
  * la persistance de revue -> Supabase (stockflow_reviews, partagee) ;
  * l'authentification      -> Supabase Auth (email / mot de passe).

Produit un fichier statique deployable (webapp/app_supabase.html). Il charge
supabase-js depuis un CDN : c'est donc un fichier a HEBERGER (il ne peut pas
etre publie comme Artifact, dont la CSP bloque les scripts externes).

Cles PUBLIQUES uniquement (memes que l'app FK Team Planner existante). La cle
service_role n'est jamais ici : elle sert uniquement au push cote serveur.
"""

from __future__ import annotations

from pathlib import Path

from build_prototype import HTML_TEMPLATE, font_face_css

ROOT = Path(__file__).resolve().parent

# Config publique (identique a index.html du FK Team Planner)
SUPABASE_URL = "https://yeusqubxgxchigssobma.supabase.co"
SUPABASE_KEY = "sb_publishable_FkwKSPbHO3CPHdRvt35img__s3HSY5R"


def _extract():
    tpl = HTML_TEMPLATE.replace("/*__FONTFACE__*/", font_face_css())
    css = tpl[tpl.index("<style>"):tpl.index("</style>") + len("</style>")]
    markup = tpl[tpl.index("<body>") + len("<body>"):tpl.index('<script id="data"')]
    after_data = tpl.index("</script>", tpl.index('<script id="data"')) + len("</script>")
    js_open = tpl.index("<script>", after_data) + len("<script>")
    js_close = tpl.index("</script>", js_open)
    app_js = tpl[js_open:js_close]
    return css, markup, app_js


AUTH_CSS = """
<style>
.auth-overlay{position:fixed;inset:0;z-index:50;background:var(--bg);display:flex;
  align-items:center;justify-content:center}
.auth-card{background:var(--card);border:1px solid var(--line);border-radius:16px;
  padding:34px 30px;width:340px;box-shadow:var(--shadow)}
.auth-card .brandline{display:flex;align-items:center;gap:10px;margin-bottom:18px}
.auth-card .logo{width:34px;height:34px;border-radius:9px;display:grid;place-items:center;font-size:18px;
  background:linear-gradient(135deg,var(--orange),var(--orange-dark))}
.auth-card b{font-family:var(--font-display);text-transform:uppercase;letter-spacing:.05em;font-size:18px}
.auth-card label{display:block;font-size:11px;color:var(--muted);text-transform:uppercase;
  letter-spacing:.08em;margin:12px 0 5px}
.auth-card input{width:100%;padding:11px 12px;border:1px solid var(--line);border-radius:9px;
  background:var(--bg);color:var(--text);font-size:14px}
.auth-card button{width:100%;margin-top:18px;padding:12px;border:none;border-radius:9px;cursor:pointer;
  background:var(--orange);color:#fff;font-family:var(--font-display);text-transform:uppercase;
  letter-spacing:.05em;font-weight:700;font-size:14px}
.auth-err{color:var(--red);font-size:12.5px;margin-top:12px;min-height:16px}
.hidden{display:none!important}
</style>
"""

AUTH_MARKUP = """
<div id="auth" class="auth-overlay">
  <div class="auth-card">
    <div class="brandline"><span class="logo">📦</span><b>STOCKFLOW.AI</b></div>
    <div style="font-size:12.5px;color:var(--muted)">Connectez-vous pour consulter et valider les recommandations.</div>
    <label>E-mail</label><input id="email" type="email" autocomplete="username"/>
    <label>Mot de passe</label><input id="pwd" type="password" autocomplete="current-password"/>
    <button id="signin">Se connecter</button>
    <div class="auth-err" id="autherr"></div>
  </div>
</div>
"""

SUPA_JS = f"""
const SUPABASE_URL="{SUPABASE_URL}";
const SUPABASE_KEY="{SUPABASE_KEY}";
const sb = window.supabase.createClient(SUPABASE_URL, SUPABASE_KEY);
window.AUTO_BOOT = false;               // on démarre l'appli seulement apres login

let RUN=null, USER=null;
const N2ID = {{}};                       // n (ligne) -> id transfert en base

// --- Source de donnees : Supabase ---
window.bootData = async function(){{
  const {{data:runs}} = await sb.from('stockflow_runs')
    .select('*').order('created_at',{{ascending:false}}).limit(1);
  RUN = (runs && runs[0]) || null;
  if(!RUN){{ return {{meta:{{brand:'STOCKFLOW.AI',tagline:'Répartition des stocks'}},
      cols:COLS, transfers:[], kpis:{{}}, flux:[], cas_counts:{{}} }}; }}
  let rows=[], from=0;
  while(true){{
    const {{data}} = await sb.from('stockflow_transfers').select('*')
      .eq('run_id',RUN.id).order('score',{{ascending:false}}).range(from,from+999);
    if(!data||!data.length) break; rows=rows.concat(data); if(data.length<1000) break; from+=1000;
  }}
  const transfers = rows.map((r,i)=>{{
    N2ID[i+1]=r.id;
    return [i+1, r.priorite, r.score, r.marque, r.expediteur, r.destinataire, r.reference,
      r.taille, r.quantite, r.cov_dest_avant, r.cov_dest_apres, r.grille_avant, r.grille_apres,
      r.dispo_finale, r.picking_prevu, r.motif];
  }});
  // synthese flux calculee cote client
  const fmap={{}};
  transfers.forEach(t=>{{ const k=t[4]+'>'+t[5]; (fmap[k]=fmap[k]||{{exp:t[4],dest:t[5],refs:new Set(),
    pieces:0,score:0,n:0}}); fmap[k].refs.add(t[6]); fmap[k].pieces+=(+t[8]||0);
    fmap[k].score+=(+t[2]||0); fmap[k].n++; }});
  const flux=Object.values(fmap).map(f=>[f.exp,f.dest,f.refs.size,f.pieces,
    Math.round(f.score/f.n*10)/10,'',Math.max(1,Math.ceil(f.pieces/30))]);
  return {{
    meta:{{brand:'STOCKFLOW.AI', tagline:'Répartition des stocks',
      runid:RUN.id, perimetre:RUN.perimetre, cible:RUN.cible, date:RUN.date_execution}},
    cols:COLS, transfers, kpis:RUN.kpis||{{}}, flux, cas_counts:{{}}
  }};
}};

// --- Persistance de revue : Supabase (partagee) ---
window.ReviewStore = {{
  async load(){{
    if(!RUN) return {{}};
    const {{data}} = await sb.from('stockflow_reviews').select('transfer_id,etat')
      .eq('run_id',RUN.id).eq('reviewer',USER.id);
    const id2etat={{}}; (data||[]).forEach(r=>id2etat[r.transfer_id]=r.etat);
    const out={{}}; Object.keys(N2ID).forEach(n=>{{ const e=id2etat[N2ID[n]]; if(e) out[n]=e; }});
    return out;
  }},
  async set(n,val){{
    const tid=N2ID[n]; if(!tid) return;
    if(val){{ await sb.from('stockflow_reviews').upsert(
        {{transfer_id:tid, run_id:RUN.id, etat:val, reviewer:USER.id, updated_at:new Date().toISOString()}},
        {{onConflict:'transfer_id,reviewer'}}); }}
    else {{ await sb.from('stockflow_reviews').delete().match({{transfer_id:tid, reviewer:USER.id}}); }}
  }}
}};

// COLS doit correspondre a l'ordre attendu par le rendu
const COLS=["n","prio","score","marque","exp","dest","ref","taille","qte","covA","covB",
  "gridA","gridB","dispoB","pick","motif"];

// --- Authentification ---
async function enter(session){{
  USER=session.user;
  document.getElementById('auth').classList.add('hidden');
  await window.boot();
}}
document.getElementById('signin').onclick=async()=>{{
  const err=document.getElementById('autherr'); err.textContent='';
  const email=document.getElementById('email').value.trim();
  const password=document.getElementById('pwd').value;
  const {{data,error}}=await sb.auth.signInWithPassword({{email,password}});
  if(error){{ err.textContent='Connexion impossible : '+error.message; return; }}
  enter(data.session);
}};
document.getElementById('pwd').addEventListener('keydown',e=>{{ if(e.key==='Enter') document.getElementById('signin').click(); }});
// session existante : on attend que l'appli (window.boot) soit definie
window.addEventListener('DOMContentLoaded', ()=>{{
  sb.auth.getSession().then(({{data}})=>{{ if(data.session) enter(data.session); }});
}});
"""


def main():
    css, markup, app_js = _extract()
    html = f"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>STOCKFLOW.AI — Répartition des stocks</title>
<script src="https://unpkg.com/@supabase/supabase-js@2"></script>
{css}
{AUTH_CSS}
</head>
<body>
{AUTH_MARKUP}
{markup}
<script>
{SUPA_JS}
</script>
<script>
{app_js}
</script>
</body>
</html>"""
    out = ROOT / "app_supabase.html"
    out.write_text(html, encoding="utf-8")
    print(f"Appli Supabase ecrite : {out} ({out.stat().st_size/1024:.0f} Ko)")


if __name__ == "__main__":
    main()
