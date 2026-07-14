"""Genere un prototype cliquable (HTML autonome) de l'interface StockFlow AI.

Lit un export Excel (+ la fiche de revue pour la marque) et produit une page web
autonome, sans dependance externe, avec :
 - navigation par onglets (Transferts, Par magasin, Synthese flux, Simulation,
   Cas non traites) ;
 - revue OK/NON integree (persistee dans le navigateur) + export CSV des valides ;
 - vue par magasin (recoit / envoie).

Identite visuelle reprise du FK Team Planner (barre laterale sombre, accent
orange, police systeme facon Inter). Ce prototype valide l'ergonomie avant le
cablage a Supabase (version hebergee multi-utilisateurs).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
EXPORTS = ROOT.parent / "exports"


def _clean(v):
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return round(float(v), 1)
    if pd.isna(v):
        return ""
    return v


def build_data(export_xlsx: Path, fiche_xlsx: Path | None, meta: dict) -> dict:
    x = pd.ExcelFile(export_xlsx)
    t = x.parse("1-Transferts")
    # marque depuis la fiche si dispo
    marque = {}
    if fiche_xlsx and Path(fiche_xlsx).exists():
        f = pd.read_excel(fiche_xlsx, sheet_name="Revue")
        if "Marque" in f.columns:
            key = "Reference (code-barre)"
            marque = dict(zip(zip(f[key].astype(str), f["Taille"].astype(str), f["Expediteur"].astype(str)),
                              f["Marque"].astype(str)))

    def mq(row):
        return marque.get((str(row["Reference (code-barre)"]), str(row["Taille"]), str(row["Expediteur"])), "")

    transfers = []
    for i, r in t.reset_index(drop=True).iterrows():
        transfers.append([
            i + 1,
            str(r["Priorite"]),
            _clean(r["Score"]),
            mq(r),
            str(r["Expediteur"]),
            str(r["Destinataire"]),
            str(r["Reference (code-barre)"]),
            str(r["Taille"]),
            _clean(r["Quantite"]),
            _clean(r["Couv. destinataire avant"]),
            _clean(r["Couv. destinataire apres"]),
            str(r["Grille avant"]),
            str(r["Grille apres"]),
            str(r["Dispo destinataire finale (par taille)"]),
            _clean(r["Reassort Picking prevu"]),
            str(r["Motif du transfert"]),
        ])

    sim = x.parse("3-Simulation")
    kpis = {str(row["indicateur"]): {"avant": _clean(row["avant"]), "apres": _clean(row["apres"])}
            for _, row in sim.iterrows()}

    flux = x.parse("2-Synthese flux")
    flux_rows = [[str(r["expediteur"]), str(r["destinataire"]), _clean(r["nb_references"]),
                  _clean(r["nb_pieces"]), _clean(r["score_moyen"]), str(r["priorite"]),
                  _clean(r["nb_colis_estime"])] for _, r in flux.iterrows()]

    cas = x.parse("5-Cas non traites")
    cas_counts = cas["categorie"].value_counts().to_dict() if "categorie" in cas else {}
    cas_counts = {str(k): int(v) for k, v in cas_counts.items()}

    return {
        "meta": meta,
        "cols": ["n", "prio", "score", "marque", "exp", "dest", "ref", "taille",
                 "qte", "covA", "covB", "gridA", "gridB", "dispoB", "pick", "motif"],
        "transfers": transfers,
        "kpis": kpis,
        "flux": flux_rows,
        "cas_counts": cas_counts,
    }


HTML_TEMPLATE = r"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>StockFlow AI — Recommandations de transferts</title>
<style>
/*__FONTFACE__*/
:root{
  /* Police d'affichage des titres : Montserrat ExtraBold (embarquee) */
  --font-display:'FKDisplay','Montserrat','Arial Narrow',ui-sans-serif,system-ui,sans-serif;
  --font-body:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
  /* DARK = identite primaire (facon FK.RESIZING) */
  --bg:#0a0a0b; --card:#141416; --card2:#1a1a1d; --line:#2a2a2f;
  --text:#f4f4f5; --muted:#8a8a92;
  --orange:#FF6B35; --orange-dark:#E85528; --orange-soft:rgba(255,107,53,.12);
  --sidebar-bg:#101012; --sidebar-hover:#1c1c20; --sidebar-text:#8a8a92;
  --green:#37d67a; --green-bg:rgba(55,214,122,.15);
  --amber:#f5a623; --amber-bg:rgba(245,166,35,.15);
  --red:#ff5a5f; --red-bg:rgba(255,90,95,.15);
  --blue:#4aa3ff; --blue-bg:rgba(74,163,255,.15);
  --shadow:0 1px 2px rgba(0,0,0,.5);
}
:root[data-theme="light"]{
  --bg:#f0f2f5; --card:#ffffff; --card2:#f7f8fa; --line:#e5e7eb;
  --text:#111827; --muted:#6b7280; --orange-soft:rgba(255,107,53,.10);
  --sidebar-bg:#1a1d29; --sidebar-hover:#252836; --sidebar-text:#9ca3af;
  --green:#16a34a; --green-bg:#dcfce7; --amber:#d97706; --amber-bg:#fef3c7;
  --red:#dc2626; --red-bg:#fee2e2; --blue:#2563eb; --blue-bg:#dbeafe;
  --shadow:0 1px 3px rgba(16,24,40,.08);
}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:var(--font-body);
  background:var(--bg);color:var(--text);display:flex;min-height:100vh;font-size:14px}
/* Sidebar */
.sidebar{width:230px;background:var(--sidebar-bg);color:#fff;display:flex;flex-direction:column;
  position:sticky;top:0;height:100vh;flex-shrink:0}
.brand{padding:20px 18px;display:flex;align-items:center;gap:10px;border-bottom:1px solid #ffffff14}
.brand .logo{width:32px;height:32px;border-radius:8px;background:linear-gradient(135deg,var(--orange),var(--orange-dark));
  display:grid;place-items:center;font-size:18px}
.brand b{font-family:var(--font-display);font-size:15px;font-weight:800;text-transform:uppercase;
  letter-spacing:.08em;white-space:nowrap;line-height:1.1}
.brand span{display:block;font-size:10.5px;letter-spacing:.03em;color:var(--sidebar-text)}
.nav{padding:12px 10px;display:flex;flex-direction:column;gap:2px;flex:1}
.nav button{all:unset;display:flex;align-items:center;gap:11px;padding:11px 12px;border-radius:9px;
  color:var(--sidebar-text);cursor:pointer;font-family:var(--font-display);font-weight:700;
  text-transform:uppercase;letter-spacing:.08em;font-size:13px}
.nav button .ico{width:18px;text-align:center}
.nav button:hover{background:var(--sidebar-hover);color:#fff}
.nav button.active{background:var(--orange);color:#fff}
.nav .count{margin-left:auto;font-size:11px;background:#ffffff22;padding:1px 7px;border-radius:20px}
.nav button.active .count{background:#ffffff33}
.side-foot{padding:14px;border-top:1px solid #ffffff14;font-size:11px;color:var(--sidebar-text)}
/* Main */
.main{flex:1;min-width:0;display:flex;flex-direction:column}
.topbar{background:var(--card);border-bottom:1px solid var(--line);padding:14px 24px;
  display:flex;align-items:center;gap:16px;position:sticky;top:0;z-index:5}
.topbar h1{font-family:var(--font-display);font-size:20px;font-weight:800;
  text-transform:uppercase;letter-spacing:.06em}
.topbar .sub{font-size:12px;color:var(--muted)}
.spacer{flex:1}
.theme-btn{all:unset;cursor:pointer;padding:7px 10px;border-radius:8px;border:1px solid var(--line);font-size:13px}
.review-pill{display:flex;gap:10px;align-items:center;font-size:12px;color:var(--muted)}
.review-pill b{color:var(--text)}
.tb-brand{display:none;align-items:center;gap:8px}
.tb-brand .tb-logo{width:26px;height:26px;border-radius:7px;
  background:linear-gradient(135deg,var(--orange),var(--orange-dark));display:grid;place-items:center;font-size:15px}
.tb-brand b{font-family:var(--font-display);text-transform:uppercase;letter-spacing:.05em;font-size:16px}
.mnav{display:none}
.content{padding:22px 24px;flex:1}
.section{display:none}.section.active{display:block}
/* KPI */
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:14px;margin-bottom:22px}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;box-shadow:var(--shadow)}
.kpi .label{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.09em;font-weight:600}
.kpi .val{font-family:var(--font-display);font-size:30px;font-weight:800;margin-top:8px;
  letter-spacing:.02em;font-variant-numeric:tabular-nums;line-height:1}
.kpi .delta{font-size:12px;margin-top:3px;font-variant-numeric:tabular-nums}
.delta.good{color:var(--green)}.delta.bad{color:var(--red)}
/* Toolbar */
.toolbar{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-bottom:14px}
.toolbar input,.toolbar select{padding:9px 12px;border:1px solid var(--line);border-radius:9px;
  background:var(--card);color:var(--text);font-size:13px}
.toolbar input[type=search]{min-width:230px}
.chips{display:flex;gap:6px;flex-wrap:wrap}
.chip{all:unset;cursor:pointer;padding:7px 13px;border-radius:20px;border:1px solid var(--line);
  font-family:var(--font-display);text-transform:uppercase;letter-spacing:.05em;font-weight:600;
  font-size:11.5px;color:var(--muted);background:transparent}
.chip:hover{border-color:var(--orange);color:var(--orange)}
.chip.on{background:var(--orange-soft);color:var(--orange);border-color:var(--orange)}
.btn{all:unset;cursor:pointer;padding:9px 14px;border-radius:9px;background:var(--orange);color:#fff;
  font-weight:600;font-size:13px}
.btn.ghost{background:transparent;border:1px solid var(--line);color:var(--text)}
/* Table */
.tablewrap{background:var(--card);border:1px solid var(--line);border-radius:12px;overflow:auto;box-shadow:var(--shadow)}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{padding:10px 12px;text-align:left;border-bottom:1px solid var(--line);white-space:nowrap}
th{position:sticky;top:0;background:var(--card);font-family:var(--font-display);font-size:11px;
  text-transform:uppercase;letter-spacing:.07em;font-weight:600;color:var(--muted);z-index:1}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
tr:hover td{background:color-mix(in srgb,var(--orange) 5%,transparent)}
.pill{display:inline-block;padding:3px 10px;border-radius:20px;font-family:var(--font-display);
  font-size:10.5px;font-weight:600;text-transform:uppercase;letter-spacing:.05em;border:1px solid transparent}
.p-Prioritaire{background:var(--green-bg);color:var(--green)}
.p-Fortement{background:var(--green-bg);color:var(--green)}
.p-Recommande{background:var(--amber-bg);color:var(--amber)}
.p-Avalider{background:var(--blue-bg);color:var(--blue)}
.flow{font-weight:600}.flow .arrow{color:var(--orange);margin:0 5px}
.motif{color:var(--muted);font-size:12px;white-space:normal;max-width:340px}
.dispo{font-variant-numeric:tabular-nums;font-size:12.5px}
.rev{display:flex;gap:5px}
.rev button{all:unset;cursor:pointer;width:30px;height:26px;border-radius:7px;text-align:center;
  border:1px solid var(--line);font-size:13px;line-height:26px}
.rev button.ok.on{background:var(--green);color:#fff;border-color:var(--green)}
.rev button.no.on{background:var(--red);color:#fff;border-color:var(--red)}
tr.reviewed-ok{background:color-mix(in srgb,var(--green) 6%,transparent)}
tr.reviewed-no{opacity:.55}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:18px}
.panel{background:var(--card);border:1px solid var(--line);border-radius:12px;box-shadow:var(--shadow)}
.panel h3{font-family:var(--font-display);font-size:13px;font-weight:700;text-transform:uppercase;
  letter-spacing:.06em;padding:14px 16px;border-bottom:1px solid var(--line);display:flex;gap:8px;align-items:center}
.panel .badge{margin-left:auto;font-size:12px;color:var(--muted)}
.empty{padding:26px;text-align:center;color:var(--muted);font-size:13px}
.note{font-size:12px;color:var(--muted);margin:10px 2px}
.mnav button{all:unset;cursor:pointer;padding:8px 13px;border-radius:8px;white-space:nowrap;
  font-family:var(--font-display);text-transform:uppercase;letter-spacing:.05em;font-weight:600;
  font-size:12px;color:var(--muted);border:1px solid var(--line)}
.mnav button.active{background:var(--orange);color:#fff;border-color:var(--orange)}
@media(max-width:820px){
  .sidebar{display:none}
  .grid2{grid-template-columns:1fr}
  .tb-brand{display:flex}
  .topbar h1{font-size:15px}
  .topbar .sub{display:none}
  .mnav{display:flex;gap:7px;overflow-x:auto;padding:10px 16px;background:var(--card);
    border-bottom:1px solid var(--line);position:sticky;top:57px;z-index:4}
  .content{padding:16px}
}
</style>
</head>
<body>
<aside class="sidebar">
  <div class="brand"><div class="logo">📦</div><div><b>StockFlow AI</b><span>Recommandations</span></div></div>
  <nav class="nav" id="nav"></nav>
  <div class="side-foot" id="foot"></div>
</aside>
<div class="main">
  <div class="topbar">
    <div class="tb-brand"><span class="tb-logo">📦</span><b id="tbBrand"></b></div>
    <div><h1 id="ttl">Transferts recommandes</h1><div class="sub" id="sub"></div></div>
    <div class="spacer"></div>
    <div class="review-pill" id="revsum"></div>
    <button class="theme-btn" id="theme">◐ Theme</button>
  </div>
  <nav class="mnav" id="mnav"></nav>
  <div class="content" id="content"></div>
</div>
<script id="data" type="application/json">/*__DATA__*/</script>
<script>
// DATA et la persistance de revue sont fournis par le "shell" (prototype ou
// Supabase). Par defaut : donnees inlinees + revue en localStorage.
let DATA = null, C = {}, reviews = {};
window.bootData = window.bootData || (async () =>
  JSON.parse(document.getElementById('data').textContent));
window.ReviewStore = window.ReviewStore || {
  async load(){ try{return JSON.parse(localStorage.getItem('sf_'+(DATA.meta.runid||'run'))||'{}')}catch(e){return {}} },
  async set(n,val){ localStorage.setItem('sf_'+(DATA.meta.runid||'run'), JSON.stringify(reviews)); }
};
const fmt = n => (typeof n==='number'? n.toLocaleString('fr-FR'):n);
const pcls = p => 'p-'+String(p).replace(/[^A-Za-z]/g,'').slice(0,10).replace('Fortementrecommande','Fortement').replace('Avalider','Avalider');

const TABS = [
  {id:'transferts',ico:'📦',label:'Transferts'},
  {id:'magasin',ico:'🏬',label:'Par magasin'},
  {id:'flux',ico:'🔀',label:'Synthese flux'},
  {id:'simulation',ico:'📊',label:'Simulation'},
  {id:'cas',ico:'⚠️',label:'Cas non traites'},
];
let tab='transferts';
const F={q:'',prio:'',boutique:'',etat:''};

function nav(){
  document.getElementById('nav').innerHTML = TABS.map(t=>`
    <button data-tab="${t.id}" class="${t.id===tab?'active':''}">
      <span class="ico">${t.ico}</span>${t.label}
      ${t.id==='transferts'?`<span class="count">${DATA.transfers.length}</span>`:''}
    </button>`).join('');
  document.getElementById('mnav').innerHTML = TABS.map(t=>`
    <button data-tab="${t.id}" class="${t.id===tab?'active':''}">${t.ico} ${t.label}</button>`).join('');
  document.querySelectorAll('#nav button, #mnav button').forEach(b=>b.onclick=()=>{tab=b.dataset.tab;render();
    document.getElementById('content').scrollIntoView({block:'start'});});
  document.getElementById('foot').innerHTML =
    `Perimetre : ${DATA.meta.perimetre||'-'}<br>Cible ${DATA.meta.cible||'-'} j · ${DATA.meta.date||''}`;
}

function reviewSummary(){
  let ok=0,no=0; Object.values(reviews).forEach(v=>{if(v==='ok')ok++;else if(v==='no')no++;});
  const tot=DATA.transfers.length;
  document.getElementById('revsum').innerHTML =
    `<span>✅ <b>${ok}</b> OK</span><span>⛔ <b>${no}</b> NON</span><span>⏳ <b>${tot-ok-no}</b> a revoir</span>`;
}

function kpiStrip(){
  const k=DATA.kpis; const cov=k.couverture_moyenne, rup=k.ruptures, sc=k.score_sante_reseau, nb=k.nb_transferts;
  const card=(label,val,delta,good)=>`<div class="kpi"><div class="label">${label}</div>
    <div class="val">${val}</div>${delta!==undefined?`<div class="delta ${good?'good':'bad'}">${delta}</div>`:''}</div>`;
  return `<div class="kpis">
    ${card('Transferts recommandes', fmt(nb.apres))}
    ${card('Ruptures', fmt(rup.apres), (rup.apres-rup.avant)+' vs '+fmt(rup.avant), rup.apres<=rup.avant)}
    ${card('Couverture moyenne', cov.apres+' j', '+'+(cov.apres-cov.avant).toFixed(1)+' j', cov.apres>=cov.avant)}
    ${card('Score sante reseau', sc.apres, '+'+(sc.apres-sc.avant).toFixed(1), sc.apres>=sc.avant)}
    ${card('Valeur deplacee', fmt(DATA.kpis.valeur_stock_deplace.apres)+' €')}
  </div>`;
}

function filtered(){
  return DATA.transfers.filter(r=>{
    if(F.prio && r[C.prio]!==F.prio) return false;
    if(F.boutique && r[C.exp]!==F.boutique && r[C.dest]!==F.boutique) return false;
    if(F.etat){ const s=reviews[r[C.n]]||'todo'; if(F.etat==='todo'&&s!=='todo')return false;
      if(F.etat==='ok'&&s!=='ok')return false; if(F.etat==='no'&&s!=='no')return false; }
    if(F.q){ const q=F.q.toLowerCase();
      if(!(String(r[C.ref]).toLowerCase().includes(q)||String(r[C.exp]).toLowerCase().includes(q)
        ||String(r[C.dest]).toLowerCase().includes(q)||String(r[C.marque]).toLowerCase().includes(q))) return false; }
    return true;
  });
}

function boutiques(){
  const s=new Set(); DATA.transfers.forEach(r=>{s.add(r[C.exp]);s.add(r[C.dest])}); return [...s].sort();
}

function transfersRow(r){
  const st=reviews[r[C.n]]||'todo';
  const cls=st==='ok'?'reviewed-ok':st==='no'?'reviewed-no':'';
  return `<tr class="${cls}" data-n="${r[C.n]}">
    <td class="num">${r[C.n]}</td>
    <td><span class="pill ${pcls(r[C.prio])}">${r[C.prio]}</span></td>
    <td class="num">${r[C.score]}</td>
    <td>${r[C.marque]}</td>
    <td class="flow">${r[C.exp]}<span class="arrow">→</span>${r[C.dest]}</td>
    <td>${r[C.ref]}</td>
    <td>${r[C.taille]}</td>
    <td class="num">${r[C.qte]}</td>
    <td class="num">${r[C.covA]}→${r[C.covB]} j</td>
    <td class="dispo">${r[C.dispoB]}</td>
    <td class="motif">${r[C.motif]}</td>
    <td><div class="rev">
      <button class="ok ${st==='ok'?'on':''}" data-a="ok" title="Valider">✓</button>
      <button class="no ${st==='no'?'on':''}" data-a="no" title="Refuser">✕</button>
    </div></td></tr>`;
}

function bindReview(root){
  root.querySelectorAll('tr[data-n] .rev button').forEach(b=>{
    b.onclick=()=>{ const tr=b.closest('tr'); const n=tr.dataset.n; const a=b.dataset.a;
      reviews[n]= reviews[n]===a? undefined : a; if(!reviews[n]) delete reviews[n];
      window.ReviewStore.set(n, reviews[n]); const st=reviews[n]||'todo';
      tr.className = st==='ok'?'reviewed-ok':st==='no'?'reviewed-no':'';
      tr.querySelectorAll('.rev button').forEach(x=>x.classList.toggle('on', reviews[n]===x.dataset.a));
      reviewSummary();
    };
  });
}

function renderTransferts(){
  const rows=filtered();
  const chips=['','Prioritaire','Fortement recommande','Recommande','A valider']
    .map(p=>`<button class="chip ${F.prio===p?'on':''}" data-prio="${p}">${p||'Toutes priorites'}</button>`).join('');
  const opts=boutiques().map(b=>`<option ${F.boutique===b?'selected':''}>${b}</option>`).join('');
  return kpiStrip()+`
  <div class="toolbar">
    <input type="search" id="q" placeholder="Rechercher reference, marque, magasin…" value="${F.q}">
    <div class="chips">${chips}</div>
    <select id="boutique"><option value="">Toutes boutiques</option>${opts}</select>
    <select id="etat">
      <option value="">Tous etats</option><option value="todo" ${F.etat==='todo'?'selected':''}>A revoir</option>
      <option value="ok" ${F.etat==='ok'?'selected':''}>Validés</option><option value="no" ${F.etat==='no'?'selected':''}>Refusés</option>
    </select>
    <div class="spacer"></div>
    <button class="btn" id="exp">⬇️ Exporter les validés (CSV)</button>
  </div>
  <div class="note">${rows.length} transfert(s) affiché(s) sur ${DATA.transfers.length}. Cliquez ✓ / ✕ pour valider ou refuser — la revue est enregistrée.</div>
  <div class="tablewrap"><table><thead><tr>
    <th class="num">N°</th><th>Priorité</th><th class="num">Score</th><th>Marque</th>
    <th>Flux</th><th>Réf. (code-barre)</th><th>Taille</th><th class="num">Qté</th>
    <th class="num">Couv. dest.</th><th>Dispo finale (dest.)</th><th>Motif</th><th>Revue</th>
  </tr></thead><tbody>${rows.slice(0,1200).map(transfersRow).join('')}</tbody></table></div>
  ${rows.length>1200?`<div class="note">Affichage limité à 1200 lignes — affinez les filtres pour voir le reste.</div>`:''}`;
}

function renderMagasin(){
  const bs=boutiques();
  const sel=F.boutique||bs[0];
  const opts=bs.map(b=>`<option ${b===sel?'selected':''}>${b}</option>`).join('');
  const recoit=DATA.transfers.filter(r=>r[C.dest]===sel);
  const envoie=DATA.transfers.filter(r=>r[C.exp]===sel);
  const mini=(arr,who)=>arr.length? `<div class="tablewrap"><table><thead><tr>
      <th>${who}</th><th>Réf.</th><th>Taille</th><th class="num">Qté</th><th class="num">Score</th><th>Dispo finale</th>
    </tr></thead><tbody>${arr.slice(0,400).map(r=>`<tr>
      <td class="flow">${who==='Depuis'?r[C.exp]:r[C.dest]}</td><td>${r[C.ref]}</td><td>${r[C.taille]}</td>
      <td class="num">${r[C.qte]}</td><td class="num">${r[C.score]}</td><td class="dispo">${r[C.dispoB]}</td>
    </tr>`).join('')}</tbody></table></div>` : `<div class="empty">Aucun mouvement.</div>`;
  const pcs=a=>a.reduce((s,r)=>s+(+r[C.qte]||0),0);
  return `<div class="toolbar"><label>Magasin&nbsp;</label>
    <select id="boutiqueM">${opts}</select></div>
    <div class="kpis" style="grid-template-columns:repeat(auto-fit,minmax(150px,1fr))">
      <div class="kpi"><div class="label">Reçoit</div><div class="val">${recoit.length}</div><div class="delta">${pcs(recoit)} pièces</div></div>
      <div class="kpi"><div class="label">Envoie</div><div class="val">${envoie.length}</div><div class="delta">${pcs(envoie)} pièces</div></div>
    </div>
    <div class="grid2">
      <div class="panel"><h3>📥 Reçoit <span class="badge">${recoit.length} lignes</span></h3>${mini(recoit,'Depuis')}</div>
      <div class="panel"><h3>📤 Envoie <span class="badge">${envoie.length} lignes</span></h3>${mini(envoie,'Vers')}</div>
    </div>`;
}

function renderFlux(){
  const rows=DATA.flux.sort((a,b)=>b[4]-a[4]);
  return `<div class="note">Regroupement logistique : un flux = un couple expéditeur → destinataire.</div>
    <div class="tablewrap"><table><thead><tr>
    <th>Expéditeur</th><th>Destinataire</th><th class="num">Réfs</th><th class="num">Pièces</th>
    <th class="num">Score moyen</th><th>Priorité</th><th class="num">Colis est.</th>
    </tr></thead><tbody>${rows.map(r=>`<tr>
      <td class="flow">${r[0]}</td><td class="flow">${r[1]}</td><td class="num">${r[2]}</td>
      <td class="num">${r[3]}</td><td class="num">${r[4]}</td><td><span class="pill ${pcls(r[5])}">${r[5]}</span></td>
      <td class="num">${r[6]}</td></tr>`).join('')}</tbody></table></div>`;
}

function renderSimulation(){
  const labels={stock_total:'Stock total',valeur_stock:'Valeur du stock (€)',stock_dormant:'Stock dormant',
    ruptures:'Ruptures',refs_sous_7j:'Réf. sous 7 j',refs_sous_14j:'Réf. sous 14 j',
    couverture_moyenne:'Couverture moyenne (j)',grilles_coherentes:'Grilles cohérentes',
    tailles_coeur_dispo:'Tailles cœur disponibles',score_sante_reseau:'Score santé réseau',
    nb_transferts:'Nb transferts',nb_destinations:'Nb destinations',valeur_stock_deplace:'Valeur déplacée (€)'};
  const rows=Object.entries(DATA.kpis).map(([k,v])=>{
    const d=(v.apres-v.avant); const good=/rupture|dormant|sous_/.test(k)? d<=0 : d>=0;
    return `<tr><td>${labels[k]||k}</td><td class="num">${fmt(v.avant)}</td><td class="num">${fmt(v.apres)}</td>
      <td class="num" style="color:${d===0?'var(--muted)':good?'var(--green)':'var(--red)'}">${d>0?'+':''}${fmt(+d.toFixed(1))}</td></tr>`;
  }).join('');
  return kpiStrip()+`<div class="tablewrap"><table><thead><tr><th>Indicateur</th>
    <th class="num">Avant</th><th class="num">Après</th><th class="num">Variation</th></tr></thead>
    <tbody>${rows}</tbody></table></div>`;
}

function renderCas(){
  const rows=Object.entries(DATA.cas_counts).sort((a,b)=>b[1]-a[1]).map(([k,v])=>
    `<tr><td>${k}</td><td class="num">${fmt(v)}</td></tr>`).join('');
  return `<div class="note">Synthèse des cas que le moteur n'a pas traités (et pourquoi).</div>
    <div class="tablewrap"><table><thead><tr><th>Catégorie</th><th class="num">Nombre</th></tr></thead>
    <tbody>${rows}</tbody></table></div>`;
}

function exportCSV(){
  const ok=DATA.transfers.filter(r=>reviews[r[C.n]]==='ok');
  const head=['N','Priorite','Score','Marque','Expediteur','Destinataire','Reference','Taille','Quantite','Motif'];
  const lines=[head.join(';')].concat(ok.map(r=>[r[C.n],r[C.prio],r[C.score],r[C.marque],r[C.exp],r[C.dest],
    r[C.ref],r[C.taille],r[C.qte],'"'+String(r[C.motif]).replace(/"/g,'""')+'"'].join(';')));
  const blob=new Blob(['﻿'+lines.join('\n')],{type:'text/csv'});
  const a=document.createElement('a'); a.href=URL.createObjectURL(blob);
  a.download='transferts_valides.csv'; a.click();
}

function render(){
  nav(); reviewSummary();
  const T=TABS.find(t=>t.id===tab);
  document.getElementById('ttl').textContent = {transferts:'Transferts recommandés',magasin:'Vue par magasin',
    flux:'Synthèse par flux',simulation:'Simulation avant / après',cas:'Cas non traités'}[tab];
  document.getElementById('sub').textContent = DATA.meta.perimetre+' · '+DATA.transfers.length+' transferts · cible '+DATA.meta.cible+' j';
  const c=document.getElementById('content');
  c.className='content';
  c.innerHTML = {transferts:renderTransferts,magasin:renderMagasin,flux:renderFlux,
    simulation:renderSimulation,cas:renderCas}[tab]();
  if(tab==='transferts'){
    bindReview(c);
    c.querySelector('#q').oninput=e=>{F.q=e.target.value;const w=c.querySelector('.tablewrap');
      const rows=filtered();w.querySelector('tbody').innerHTML=rows.slice(0,1200).map(transfersRow).join('');bindReview(w);
      c.querySelector('.note').textContent=`${rows.length} transfert(s) affiché(s) sur ${DATA.transfers.length}.`;};
    c.querySelectorAll('.chip').forEach(ch=>ch.onclick=()=>{F.prio=ch.dataset.prio;render()});
    c.querySelector('#boutique').onchange=e=>{F.boutique=e.target.value;render()};
    c.querySelector('#etat').onchange=e=>{F.etat=e.target.value;render()};
    c.querySelector('#exp').onclick=exportCSV;
  }
  if(tab==='magasin'){ c.querySelector('#boutiqueM').onchange=e=>{F.boutique=e.target.value;render()}; }
}

document.getElementById('theme').onclick=()=>{
  const r=document.documentElement; const cur=r.getAttribute('data-theme')||'dark';
  r.setAttribute('data-theme', cur==='light'?'dark':'light');
};

window.boot = async function(){
  DATA = await window.bootData();
  C = {}; DATA.cols.forEach((c,i)=>C[c]=i);
  const BRAND = DATA.meta.brand || 'StockFlow AI';
  document.querySelector('.brand b').textContent = BRAND;
  document.querySelector('.brand span').textContent = DATA.meta.tagline || 'Recommandations';
  document.getElementById('tbBrand').textContent = BRAND;
  document.title = BRAND + ' — Recommandations de transferts';
  reviews = await window.ReviewStore.load();
  render();
};
if(window.AUTO_BOOT !== false) window.boot();
</script>
</body>
</html>"""


def font_face_css() -> str:
    """Embarque la police d'affichage (titres) en data-URI.

    Cherche webapp/display.woff2 (ou .woff/.ttf/.otf) et l'embarque sous la
    famille 'FKDisplay' (la CSP interdit le chargement depuis un CDN). Ici :
    Montserrat ExtraBold. En l'absence de fichier, repli bold/majuscules.
    """
    import base64
    for name, fmt in [("display.woff2", "woff2"), ("display.woff", "woff"),
                      ("display.ttf", "truetype"), ("display.otf", "opentype")]:
        p = ROOT / name
        if p.exists():
            b64 = base64.b64encode(p.read_bytes()).decode()
            return (f"@font-face{{font-family:'FKDisplay';"
                    f"src:url('data:font/{fmt};base64,{b64}') format('{fmt}');"
                    f"font-weight:400 900;font-style:normal;font-display:swap}}")
    return ("/* Police d'affichage non fournie : deposez webapp/display.woff2 "
            "puis relancez build_prototype.py. */")


def main():
    export = EXPORTS / "stockflow_dispo.xlsx"
    fiche = EXPORTS / "fiche_revue_dispo.xlsx"
    meta = {"runid": "perimetre_14j", "brand": "STOCKFLOW.AI",
            "tagline": "Répartition des stocks",
            "perimetre": "24 boutiques actives", "cible": 14, "date": "12/07/2026"}
    data = build_data(export, fiche, meta)
    payload = json.dumps(data, ensure_ascii=False)
    html = (HTML_TEMPLATE
            .replace("/*__FONTFACE__*/", font_face_css())
            .replace("/*__DATA__*/", payload))
    out = ROOT / "stockflow_prototype.html"
    out.write_text(html, encoding="utf-8")

    # version "contenu seul" pour publication en Artifact (le squelette
    # <!doctype>/<head>/<body> est ajoute a la publication)
    style = html[html.find("<style>"):html.find("</style>") + 8]
    body = html[html.find("<body>") + 6:html.rfind("</body>")]
    artifact = (f"<title>{meta['brand']} — Répartition des stocks</title>\n"
                + style + "\n" + body)
    art = ROOT / "stockflow_artifact.html"
    art.write_text(artifact, encoding="utf-8")

    # validation du JSON injecte
    json.loads(payload)
    size = out.stat().st_size / 1024
    print(f"Prototype ecrit : {out} ({size:.0f} Ko, {len(data['transfers'])} transferts)")
    print(f"Version artifact : {art} ({art.stat().st_size/1024:.0f} Ko)")


if __name__ == "__main__":
    main()
