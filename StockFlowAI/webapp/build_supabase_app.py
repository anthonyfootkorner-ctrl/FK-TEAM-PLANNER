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
# URL du backend de generation (bouton "Generer"). Vide = bouton inactif.
BACKEND_URL = "https://fk-team-planner.onrender.com"


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
  flex-direction:column;overflow:auto}
.auth-top{display:flex;align-items:center;gap:10px;padding:22px 26px;flex-shrink:0}
.auth-top .logo{width:26px;height:32px;display:grid;place-items:center}
.auth-top b{font-family:var(--font-display);text-transform:uppercase;letter-spacing:.06em;font-size:17px}
.auth-body{flex:1;display:flex;align-items:center;justify-content:center;gap:64px;
  padding:12px 26px 54px;flex-wrap:wrap}
.auth-hero{max-width:460px}
.hero-head{font-family:var(--font-display);font-weight:800;text-transform:uppercase;
  font-size:clamp(42px,8.5vw,78px);line-height:.96;letter-spacing:-.015em}
.hero-head .hl{color:var(--orange)}
.hero-sub{color:var(--muted);font-size:15px;margin-top:20px;max-width:370px;line-height:1.5}
.auth-card{background:var(--card);border:1px solid var(--line);border-radius:16px;
  padding:32px 30px;width:340px;max-width:100%;box-shadow:var(--shadow)}
.auth-card .intro{font-size:12.5px;color:var(--muted);margin-bottom:4px}
.auth-card label{display:block;font-size:11px;color:var(--muted);text-transform:uppercase;
  letter-spacing:.08em;margin:14px 0 5px}
.auth-card input{width:100%;padding:12px 12px;border:1px solid var(--line);border-radius:9px;
  background:var(--bg);color:var(--text);font-size:15px}
.auth-card button{width:100%;margin-top:20px;padding:13px;border:none;border-radius:9px;cursor:pointer;
  background:var(--orange);color:#fff;font-family:var(--font-display);text-transform:uppercase;
  letter-spacing:.05em;font-weight:700;font-size:14px}
.auth-err{color:var(--red);font-size:12.5px;margin-top:12px;min-height:16px}
.hidden{display:none!important}
@media(max-width:820px){
  .auth-body{gap:30px;padding:8px 22px 40px}
  .auth-hero{max-width:100%;flex:1 0 100%}
  .hero-sub{max-width:100%}
}
</style>
"""

LOGO_SVG = ('<svg class="fklogo" viewBox="0 0 64 80" fill="none" aria-hidden="true">'
  '<defs><linearGradient id="fkgC" x1="0" y1="0" x2="0" y2="1">'
  '<stop offset="0" stop-color="#FF9E6D"/><stop offset="1" stop-color="#EF5A2A"/></linearGradient></defs>'
  '<g stroke="url(#fkgC)" stroke-linecap="round" fill="none">'
  '<path d="M44 16C44 8 24 7 22 20C20 33 42 34 40 48C38 63 19 62 16 54" stroke-width="3.5" opacity=".45" transform="translate(-5 0)"/>'
  '<path d="M46 16C46 8 24 6 22 20C20 33 44 34 42 48C40 64 18 62 16 54" stroke-width="5"/>'
  '<path d="M48 16C48 8 26 7 24 20C22 33 46 34 44 48C42 63 21 62 18 54" stroke-width="3.5" opacity=".7" transform="translate(5 0)"/>'
  '</g><circle cx="46" cy="16" r="2.4" fill="#FF9E6D"/><circle cx="16" cy="54" r="2.4" fill="#EF5A2A"/></svg>')

AUTH_MARKUP = f"""
<div id="auth" class="auth-overlay">
  <div class="auth-top"><span class="logo">{LOGO_SVG}</span><b>stockflow.ai</b></div>
  <div class="auth-body">
    <div class="auth-hero">
      <h2 class="hero-head">ANALYSE.<br><span class="hl">OPTIMISE.</span><br>GAGNE.</h2>
      <p class="hero-sub">La répartition intelligente des stocks entre tes magasins : moins de ruptures, moins de dormant, les bonnes tailles au bon endroit.</p>
    </div>
    <div class="auth-card">
      <div class="intro">Connectez-vous pour consulter et valider les recommandations.</div>
      <label>E-mail</label><input id="email" type="email" autocomplete="username"/>
      <label>Mot de passe</label><input id="pwd" type="password" autocomplete="current-password"/>
      <button id="signin">Se connecter</button>
      <div class="auth-err" id="autherr"></div>
    </div>
  </div>
</div>
"""

SUPA_JS = f"""
const SUPABASE_URL="{SUPABASE_URL}";
const SUPABASE_KEY="{SUPABASE_KEY}";
const sb = window.supabase.createClient(SUPABASE_URL, SUPABASE_KEY);
window.AUTO_BOOT = false;               // on démarre l'appli seulement apres login

// URL du backend de generation (Render/Railway). A renseigner apres deploiement.
const BACKEND_URL = "{BACKEND_URL}";

let RUN=null, USER=null, ACCESS=null;
const N2ID = {{}};                       // n (ligne) -> id transfert en base
let ID2ROW = {{}};                       // id transfert -> ligne (pour enrichir les differences)

// --- Source de donnees : Supabase ---
// liste des runs recents (historique)
window.listRuns = async function(){{
  const {{data}} = await sb.from('stockflow_runs')
    .select('id,label,date_execution,nb_transferts,created_at')
    .order('created_at', {{ascending:false}}).limit(20);
  return data || [];
}};

window.bootData = async function(){{
  let q = sb.from('stockflow_runs').select('*');
  q = window.__runId ? q.eq('id', window.__runId).limit(1)
                     : q.order('created_at', {{ascending:false}}).limit(1);
  const {{data:runs}} = await q;
  RUN = (runs && runs[0]) || null;
  if(!RUN){{ return {{meta:{{brand:'STOCKFLOW.AI',tagline:'Répartition des stocks'}},
      cols:COLS, transfers:[], kpis:{{}}, flux:[], cas_counts:{{}} }}; }}
  let rows=[], from=0;
  while(true){{
    const {{data}} = await sb.from('stockflow_transfers').select('*')
      .eq('run_id',RUN.id).order('score',{{ascending:false}}).range(from,from+999);
    if(!data||!data.length) break; rows=rows.concat(data); if(data.length<1000) break; from+=1000;
  }}
  ID2ROW = {{}};
  const transfers = rows.map((r,i)=>{{
    N2ID[i+1]=r.id;
    const row=[i+1, r.priorite, r.score, r.marque, r.expediteur, r.destinataire, r.reference,
      r.taille, r.quantite, r.cov_dest_avant, r.cov_dest_apres, r.grille_avant, r.grille_apres,
      r.dispo_finale, r.picking_prevu, r.motif];
    ID2ROW[r.id]=row;
    return row;
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
      runid:RUN.id, perimetre:RUN.perimetre, cible:RUN.cible, date:RUN.date_execution,
      impact:RUN.impact||null, fastmag_import:RUN.fastmag_import||null}},
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

// --- Role : magasin (login mappe) vs admin ---
// Resilient : si la table n'existe pas / erreur reseau, on ne bloque pas la
// connexion, on retombe simplement en mode admin.
window.roleInfo = async function(){{
  try{{
    const {{data, error}} = await sb.from('stockflow_user_stores')
      .select('magasin').eq('user_id', USER.id).order('magasin');
    if(!error && data && data.length){{
      return {{mode:'store', stores:data.map(r=>r.magasin)}};
    }}
  }}catch(e){{ console.warn('roleInfo', e); }}
  return {{mode:'admin', stores:[]}};
}};

// --- Differences signalees par les magasins (cote admin) ---
window.DiffStore = {{
  async list(){{
    if(!RUN) return [];
    const {{data, error}} = await sb.from('stockflow_reviews')
      .select('transfer_id, updated_at').eq('run_id', RUN.id).eq('etat','diff')
      .order('updated_at', {{ascending:false}});
    if(error) throw error;
    return (data||[]).map(dd=>{{ const t=ID2ROW[dd.transfer_id]; if(!t) return null;
      return {{reference:t[6], taille:t[7], quantite:t[8], expediteur:t[4],
        destinataire:t[5], marque:t[3], updated_at:dd.updated_at}}; }}).filter(Boolean);
  }}
}};

// --- Reassort central (CENTRAL -> magasins) : sortie A + import Fastmag (B) ---
window.ReassortStore = {{
  async list(store){{
    if(!RUN) return [];
    let q = sb.from('stockflow_reassort_central').select('*').eq('run_id', RUN.id);
    if(store) q = q.eq('boutique', store);
    // tri : priorite (P1..P4) puis quantite decroissante
    q = q.order('priorite', {{ascending:true}}).order('qte', {{ascending:false}});
    const {{data, error}} = await q.limit(5000);
    if(error) throw error;
    return (data||[]).map(r=>({{boutique:r.boutique, reference:r.reference, taille:r.taille,
      marque:r.marque, qte:r.qte, priorite:r.priorite, commentaire:r.commentaire,
      couverture_j:r.couverture_j, tailles_apres:r.tailles_apres}}));
  }},
  // lien de telechargement du fichier d'import Fastmag (admin, via le backend)
  async fastmagUrl(){{
    if(!RUN || !RUN.fastmag_import || !BACKEND_URL) return null;
    try{{ const j = await _adminApi('/fastmag?path='+encodeURIComponent(RUN.fastmag_import));
      return (j && j.url) || null; }}catch(e){{ return null; }}
  }}
}};

// --- Valorisation cumulative (central / inter-magasins, credit expediteur) ---
window.ValoStore = {{
  async all(){{
    let out=[], from=0;
    while(true){{
      const {{data, error}} = await sb.from('stockflow_valorisation')
        .select('type,expediteur,destinataire,reference,cumul_units,cumul_ca,cumul_marge')
        .gt('cumul_units', 0).range(from, from+999);
      if(error) throw error;
      if(!data || !data.length) break;
      out = out.concat(data); if(data.length<1000) break; from += 1000;
    }}
    return out;
  }}
}};

// --- Donneurs : proposition de depannage sur une demande urgente ---
// La table ne contient que la photo du run courant (surplus mobilisable).
window.DonorStore = {{
  async forRef(reference, taille){{
    if(!reference) return [];
    const {{data, error}} = await sb.from('stockflow_donors')
      .select('magasin,taille,qte_don,couverture_j,motif')
      .eq('reference', reference).limit(200);
    if(error) throw error;
    return (data||[]).map(d=>({{magasin:d.magasin, taille:d.taille, qte_don:d.qte_don,
      couverture_j:d.couverture_j, motif:d.motif}}));
  }}
}};

// --- Expeditions validees par les magasins ---
window.ShipStore = {{
  async load(){{
    if(!RUN) return {{}};
    const {{data, error}} = await sb.from('stockflow_shipments')
      .select('expediteur,destinataire').eq('run_id', RUN.id);
    if(error) throw error;
    const m={{}}; (data||[]).forEach(r=>{{ m[r.expediteur+'>'+r.destinataire]=true; }}); return m;
  }},
  async validate(exp,dest){{
    const {{error}} = await sb.from('stockflow_shipments').upsert(
      {{run_id:RUN.id, expediteur:exp, destinataire:dest, statut:'validee',
        validated_by:USER.id, validated_at:new Date().toISOString()}},
      {{onConflict:'run_id,expediteur,destinataire'}});
    if(error) throw error;
  }},
  async unvalidate(exp,dest){{
    const {{error}} = await sb.from('stockflow_shipments').delete()
      .match({{run_id:RUN.id, expediteur:exp, destinataire:dest}});
    if(error) throw error;
  }}
}};

// --- Back-office utilisateurs (via le backend, protege par le jeton admin) ---
async function _adminApi(path, method, body){{
  if(!BACKEND_URL) throw new Error("Backend non configure.");
  const r = await fetch(BACKEND_URL.replace(/\\/$/, '') + path, {{
    method: method || 'GET',
    headers: {{'Authorization':'Bearer '+ACCESS, 'Content-Type':'application/json'}},
    body: body ? JSON.stringify(body) : undefined }});
  if(!r.ok){{ let m='Erreur '+r.status; try{{ const j=await r.json(); m=j.detail||m; }}catch(e){{}} throw new Error(m); }}
  return r.status===204 ? null : await r.json();
}}
window.UserAdmin = {{
  list: () => _adminApi('/users'),
  create: (email, password, stores) => _adminApi('/users', 'POST', {{email, password, stores}}),
  setStores: (id, stores) => _adminApi('/users/'+id+'/stores', 'POST', {{stores}}),
  remove: (id) => _adminApi('/users/'+id, 'DELETE')
}};

// --- Deconnexion ---
window.doLogout = async function(){{
  try{{ await sb.auth.signOut(); }}catch(e){{}}
  location.reload();
}};

// --- Demandes urgentes (magasin -> validation admin) ---
window.UrgentStore = {{
  async create(o){{ const {{error}} = await sb.from('stockflow_urgent_requests').insert(
      {{magasin:o.magasin, reference:o.reference, taille:o.taille||null, quantite:o.quantite||1,
        motif:o.motif||null, created_by:USER.id}});
    if(error) throw error; }},
  async listMine(store){{ const {{data,error}} = await sb.from('stockflow_urgent_requests').select('*')
      .eq('magasin',store).order('created_at',{{ascending:false}}); if(error) throw error; return data||[]; }},
  async listAll(){{ const {{data,error}} = await sb.from('stockflow_urgent_requests').select('*')
      .order('created_at',{{ascending:false}}); if(error) throw error; return data||[]; }},
  async decide(id,dec){{ const {{error}} = await sb.from('stockflow_urgent_requests')
      .update({{statut:dec, decided_by:USER.id, decided_at:new Date().toISOString()}}).eq('id',id);
    if(error) throw error; }}
}};

// COLS doit correspondre a l'ordre attendu par le rendu
const COLS=["n","prio","score","marque","exp","dest","ref","taille","qte","covA","covB",
  "gridA","gridB","dispoB","pick","motif"];

// --- Authentification ---
async function enter(session){{
  USER=session.user;
  ACCESS=session.access_token;
  document.getElementById('auth').classList.add('hidden');
  await window.boot();
}}

// --- Generation : envoi au relais -> calcul sur GitHub -> attente du nouveau run ---
window.doGenerate = async function({{stock, ventes, reassort, objectif, central, cible}}){{
  if(!BACKEND_URL) throw new Error("Backend non configure (BACKEND_URL vide).");
  const fd = new FormData();
  fd.append('stock', stock);
  fd.append('ventes', ventes);
  if(reassort) fd.append('reassort', reassort);
  if(objectif) fd.append('objectif', objectif);
  if(central) fd.append('central', central);
  fd.append('cible', String(cible));
  const baseId = RUN ? RUN.id : null;
  const r = await fetch(BACKEND_URL.replace(/\\/$/, '') + '/generer', {{
    method:'POST', headers:{{'Authorization':'Bearer '+ACCESS}}, body: fd }});
  if(!r.ok){{ let m='Erreur '+r.status; try{{ const j=await r.json(); m=j.detail||m; }}catch(e){{}} throw new Error(m); }}
  // fichiers envoyes : le moteur tourne sur GitHub (~1-2 min) -> etape "optimise"
  if(window.__genStep) window.__genStep('optimise');
  if(window.__onGenProgress) window.__onGenProgress("Optimisation des transferts…");
  for(let i=0; i<42; i++){{               // ~7 min max (10 s x 42)
    await new Promise(res=>setTimeout(res, 10000));
    const {{data}} = await sb.from('stockflow_runs').select('id,nb_transferts,perimetre')
      .order('created_at', {{ascending:false}}).limit(1);
    const latest = data && data[0];
    if(latest && latest.id !== baseId)
      return {{nb_transferts: latest.nb_transferts, perimetre: latest.perimetre}};
    if(window.__onGenProgress) window.__onGenProgress(`Optimisation des transferts… (${{(i+1)*10}} s)`);
  }}
  throw new Error("Toujours en cours — recharge la page dans 1-2 min pour voir le nouveau run.");
}};
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
