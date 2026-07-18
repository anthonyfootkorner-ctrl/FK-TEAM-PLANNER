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
  --font-body:ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
  /* DARK = identite primaire — neutres a peine tiedis vers l'orange (choisis, pas gris par defaut) */
  --bg:#0b0b0c; --card:#161513; --card2:#1d1b18; --line:#2a2825;
  --text:#f4f3f1; --muted:#8c8a85;
  --orange:#FF6B35; --orange-dark:#E85528; --orange-soft:rgba(255,107,53,.12);
  --sidebar-bg:#100f0d; --sidebar-hover:#201d19; --sidebar-text:#8c8a85;
  --green:#37d67a; --green-bg:rgba(55,214,122,.14);
  --amber:#f5a623; --amber-bg:rgba(245,166,35,.14);
  --red:#ff5a5f; --red-bg:rgba(255,90,95,.14);
  --blue:#4aa3ff; --blue-bg:rgba(74,163,255,.14);
  --shadow:0 1px 2px rgba(0,0,0,.4);
  --shadow-lift:0 6px 20px -8px rgba(0,0,0,.55);
  --radius:14px; --radius-sm:10px;
  /* easing (regles Emil Kowalski) : ease-out fort pour les entrees, jamais ease-in */
  --ease:cubic-bezier(.23,1,.32,1);
}
:root[data-theme="light"]{
  --bg:#f6f5f3; --card:#ffffff; --card2:#f4f2ef; --line:#e7e4df;
  --text:#1a1815; --muted:#6b6862; --orange-soft:rgba(255,107,53,.10);
  --sidebar-bg:#17140f; --sidebar-hover:#241f18; --sidebar-text:#a29b8f;
  --green:#16a34a; --green-bg:#dcfce7; --amber:#d97706; --amber-bg:#fef3c7;
  --red:#dc2626; --red-bg:#fee2e2; --blue:#2563eb; --blue-bg:#dbeafe;
  --shadow:0 1px 3px rgba(26,24,21,.07);
  --shadow-lift:0 8px 24px -10px rgba(26,24,21,.18);
}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:var(--font-body);
  background:var(--bg);color:var(--text);display:flex;min-height:100vh;font-size:14px}
/* Sidebar */
.sidebar{width:230px;background:var(--sidebar-bg);color:#fff;display:flex;flex-direction:column;
  position:sticky;top:0;height:100vh;flex-shrink:0}
.brand{padding:20px 18px;display:flex;align-items:center;gap:10px;border-bottom:1px solid #ffffff14}
.brand .logo{width:30px;height:36px;display:grid;place-items:center;flex-shrink:0}
.fklogo{width:100%;height:100%;display:block}
.brand b{font-family:var(--font-display);font-size:15px;font-weight:800;text-transform:uppercase;
  letter-spacing:.08em;white-space:nowrap;line-height:1.1}
.brand span{display:block;font-size:10.5px;letter-spacing:.03em;color:var(--sidebar-text)}
.nav{padding:12px 10px;display:flex;flex-direction:column;gap:1px;flex:1}
.nav button{all:unset;position:relative;display:flex;align-items:center;gap:11px;padding:10px 12px;border-radius:9px;
  color:var(--sidebar-text);cursor:pointer;font-family:var(--font-body);font-weight:550;
  letter-spacing:.005em;font-size:13.5px;transition:background .18s var(--ease),color .18s var(--ease)}
.ico{display:inline-flex;align-items:center;justify-content:center;flex-shrink:0}
.ic{width:18px;height:18px;display:block}
.nav button .ico{width:18px;color:var(--muted);transition:color .18s var(--ease)}
.nav button:hover{background:var(--sidebar-hover);color:var(--text)}
.nav button:hover .ico{color:var(--text)}
.nav button.active{background:var(--orange-soft);color:var(--orange);font-weight:650}
.nav button.active .ico{color:var(--orange)}
.nav button.active::before{content:"";position:absolute;left:0;top:9px;bottom:9px;width:3px;border-radius:3px;background:var(--orange)}
.nav .count{margin-left:auto;font-size:11px;font-variant-numeric:tabular-nums;background:#ffffff14;
  color:var(--muted);padding:1px 7px;border-radius:20px;transition:all .18s var(--ease)}
.nav button.active .count{background:var(--orange);color:#fff}
.side-foot{padding:14px;border-top:1px solid #ffffff14;font-size:11px;color:var(--sidebar-text)}
/* Main */
.main{flex:1;min-width:0;display:flex;flex-direction:column}
.topbar{background:var(--card);border-bottom:1px solid var(--line);padding:14px 24px;
  display:flex;align-items:center;gap:16px;position:sticky;top:0;z-index:5}
.topbar h1{font-family:var(--font-display);font-size:22px;font-weight:800;letter-spacing:-.01em}
.topbar .sub{font-size:12.5px;color:var(--muted);margin-top:1px}
.spacer{flex:1}
.theme-btn{all:unset;cursor:pointer;padding:7px 10px;border-radius:8px;border:1px solid var(--line);font-size:13px}
.review-pill{display:flex;gap:10px;align-items:center;font-size:12px;color:var(--muted)}
.review-pill b{color:var(--text)}
.review-pill i.w{font-style:normal}
/* Slogan d'entete (facon FK.RESIZING) : inline sur PC, defilant sur mobile */
.motto{display:flex;gap:9px;align-items:center;font-family:var(--font-display);text-transform:uppercase;
  letter-spacing:.09em;font-weight:800;font-size:13.5px;color:var(--text);white-space:nowrap}
.motto .w2{color:var(--orange)}
/* Resume de revue (dans l'onglet Transferts) */
.revsum{display:flex;flex-wrap:wrap;gap:6px 16px;font-size:13px;color:var(--muted);margin:2px 2px 14px}
.revsum b{color:var(--text)}
/* Cartes de mouvement (vue Par magasin, mobile) */
.mvlist{display:none;flex-direction:column;gap:8px;padding:10px}
.mvcard{background:var(--card2);border:1px solid var(--line);border-radius:10px;padding:11px 12px}
.mvtop{display:flex;align-items:baseline;gap:8px}
.mvstore{font-family:var(--font-display);font-weight:700;text-transform:uppercase;letter-spacing:.03em;font-size:14.5px}
.mvqte{margin-left:auto;font-variant-numeric:tabular-nums;font-weight:700;font-size:14px;white-space:nowrap}
.mvqte small{color:var(--muted);font-weight:400;font-size:11px}
.mvmeta{font-size:12.5px;color:var(--muted);margin-top:4px;font-variant-numeric:tabular-nums}
.mvdispo{font-size:12px;color:var(--muted);margin-top:2px;font-variant-numeric:tabular-nums}
/* Vue magasin (role terrain) : colonne de cartes visible partout */
.cardcol{display:flex;flex-direction:column;gap:12px}
.prepbar{height:9px;background:var(--card2);border:1px solid var(--line);border-radius:20px;overflow:hidden;margin:2px 2px 8px}
.prepbar-fill{height:100%;background:var(--green);width:0;transition:width .3s}
/* Formulaire de demande urgente */
.ufield{margin-bottom:11px}
.ufield label{display:block;font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.07em;margin-bottom:5px}
.ufield input,.ufield textarea{width:100%;box-sizing:border-box;padding:12px;border:1px solid var(--line);
  border-radius:9px;background:var(--bg);color:var(--text);font-size:15px;font-family:var(--font-body)}
.urow{display:flex;gap:10px}.urow .ufield{flex:1}
/* Cases magasins (back-office utilisateurs) */
.uchecks{display:flex;flex-wrap:wrap;gap:9px 16px}
.ucheck{display:flex;align-items:center;gap:7px;font-size:13.5px;cursor:pointer}
.ucheck input{width:16px;height:16px;accent-color:var(--orange)}
/* Switcher de magasin (comptes multi-magasins) */
.storeswitch{display:flex;align-items:center;gap:10px;margin:0 0 16px}
.storeswitch label{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.07em}
.storeswitch select{flex:1;max-width:280px;box-sizing:border-box;padding:11px 12px;border:1px solid var(--line);
  border-radius:9px;background:var(--card);color:var(--text);font-size:15px;font-weight:600}
/* Expedier — niveau 1 : cartes d'expedition fermees (par destination) */
.destcard{all:unset;box-sizing:border-box;cursor:pointer;display:flex;align-items:center;gap:12px;width:100%;
  background:var(--card);border:1px solid var(--line);border-radius:var(--radius);padding:14px 15px;margin-bottom:10px;
  box-shadow:var(--shadow);transition:transform .2s var(--ease),border-color .2s var(--ease),box-shadow .2s var(--ease)}
.destcard:hover{border-color:color-mix(in srgb,var(--orange) 45%,var(--line));transform:translateY(-2px);box-shadow:var(--shadow-lift)}
.destcard:active{transform:translateY(0)}
.destcard.alldone{border-color:var(--green)}
.destcard-main{flex:1;min-width:0}
.destcard-title{font-family:var(--font-display);font-weight:800;text-transform:uppercase;letter-spacing:.02em;font-size:16px}
.destcard-sub{font-size:12.5px;color:var(--muted);margin-top:3px}
.destcard-side{display:flex;flex-direction:column;align-items:flex-end;gap:6px}
.destprogwrap{display:flex;align-items:center;gap:7px}
.destprog{width:74px;height:6px;border-radius:20px;background:var(--card2);overflow:hidden}
.destprog span{display:block;height:100%;background:var(--green)}
.destprog-txt{font-size:11px;color:var(--muted);font-variant-numeric:tabular-nums;min-width:34px;text-align:right}
.destcard .chev{font-size:24px;color:var(--muted);line-height:1}
/* Expedier — niveau 2 : bon de prepa (lignes minimalistes) */
.prepback{all:unset;cursor:pointer;color:var(--muted);font-size:13px;margin-bottom:12px;display:inline-block}
.prepback:hover{color:var(--orange)}
.prephead{display:flex;align-items:baseline;justify-content:space-between;gap:10px;margin-bottom:14px}
.prepdest{font-family:var(--font-display);font-weight:800;text-transform:uppercase;font-size:19px}
.prepcount{font-size:13px;color:var(--muted);font-variant-numeric:tabular-nums;white-space:nowrap}
.preplist{display:flex;flex-direction:column;gap:8px}
.prepline{display:flex;align-items:center;gap:12px;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:11px 13px}
.prepinfo{flex:1;min-width:0;display:flex;align-items:baseline;gap:12px;flex-wrap:wrap}
.prepref{font-weight:700;font-size:15px}
.prepsize{font-family:var(--font-display);font-weight:800;font-size:17px;letter-spacing:.03em}
.prepqty{color:var(--muted);font-variant-numeric:tabular-nums;font-size:14px}
.prepacts{display:flex;gap:8px;flex-shrink:0}
.prepacts button{all:unset;box-sizing:border-box;cursor:pointer;width:48px;height:44px;border-radius:11px;
  border:1px solid var(--line);display:grid;place-items:center;font-size:19px;background:var(--card2)}
.prepacts .pok.on{background:var(--green);color:#fff;border-color:var(--green)}
.prepacts .pdiff.on{background:var(--amber);color:#1a1a1a;border-color:var(--amber)}
.prepline.done{border-color:var(--green)}
.prepline.done .prepref,.prepline.done .prepsize{opacity:.55;text-decoration:line-through}
.prepline.diff{border-color:var(--amber)}
/* Validation d'expedition (le magasin confirme la commande preparee) */
#prepfooter{margin-top:18px}
.shipbtn{all:unset;box-sizing:border-box;cursor:pointer;display:block;width:100%;text-align:center;
  background:var(--orange);color:#fff;font-family:var(--font-display);text-transform:uppercase;
  letter-spacing:.04em;font-weight:700;font-size:15px;padding:16px;border-radius:12px}
.shipbtn[disabled]{background:var(--card2);color:var(--muted);cursor:not-allowed;border:1px solid var(--line)}
.shipdone{display:flex;align-items:center;justify-content:center;gap:14px;background:var(--green-bg);
  color:var(--green);font-family:var(--font-display);font-weight:800;text-transform:uppercase;
  letter-spacing:.04em;padding:15px;border-radius:12px;font-size:15px}
.shipundo{all:unset;cursor:pointer;color:var(--muted);font-family:var(--font-body);text-transform:none;
  font-weight:500;font-size:12px;text-decoration:underline}
.destcard.shipped{border-color:var(--green);opacity:.75}
/* Selecteur de previsualisation magasin (pied de sidebar admin) */
.foot-sel{width:100%;box-sizing:border-box;margin-top:10px;padding:8px 10px;border:1px solid #ffffff26;
  border-radius:8px;background:var(--sidebar-hover);color:#fff;font-size:12px;cursor:pointer}
/* Boutons de decision (admin) sur une demande */
.dact{display:flex;gap:9px;margin-top:12px}
.dact button{flex:1;min-height:44px;border-radius:11px;border:1px solid var(--line);background:var(--card2);
  color:var(--text);font-family:var(--font-display);font-weight:700;text-transform:uppercase;
  letter-spacing:.04em;font-size:12.5px;cursor:pointer}
.dact button.val{background:var(--green);color:#fff;border-color:var(--green)}
.dact button.ref{background:var(--red);color:#fff;border-color:var(--red)}
/* ===== Splash d'intro (apparition douce et progressive) ===== */
#splash{position:fixed;inset:0;z-index:100;cursor:pointer;
  background:radial-gradient(circle at 50% 42%, #141519 0%, #0a0a0b 74%);
  display:flex;flex-direction:column;align-items:center;justify-content:center;gap:26px;
  transition:opacity .6s ease}
#splash.out{opacity:0;pointer-events:none}
.splash-inner{display:flex;flex-direction:column;align-items:center;gap:22px}
/* le S se dessine a partir de rien, en fondu (aucun clignotement) */
.splash-logo{width:118px;height:148px;filter:drop-shadow(0 0 10px rgba(255,107,53,.30))}
.splash-logo svg{width:100%;height:100%;overflow:visible}
/* le S part invisible et se trace progressivement */
.splash-logo g path{stroke-dasharray:230;stroke-dashoffset:230;animation:draw 1.35s ease .1s forwards}
/* une etincelle blanche/orange parcourt le trace (effet electricite) */
.splash-logo .spark{stroke-dasharray:5 100;stroke-dashoffset:105;opacity:0;
  filter:drop-shadow(0 0 5px #ffd0a0) drop-shadow(0 0 9px rgba(255,107,53,.75));
  animation:spark 1.45s ease-out .1s forwards}
.splash-logo circle{opacity:0;animation:sfade .5s 1.25s ease forwards}
.splash-words{display:flex;flex-direction:column;align-items:center;gap:1px;
  font-family:var(--font-display);font-weight:800;text-transform:uppercase;letter-spacing:.12em;
  font-size:clamp(28px,7.5vw,46px);line-height:1.04;color:#f4f4f5}
.splash-words .sw{opacity:0;transform:translateY(7px);animation:srise .6s ease forwards}
.splash-words .sw2{color:var(--orange)}
.sw1{animation-delay:.95s}.sw2{animation-delay:1.15s}.sw3{animation-delay:1.35s}
.splash-bar{width:130px;height:3px;border-radius:3px;opacity:0;
  background:linear-gradient(90deg,transparent,var(--orange),transparent);
  animation:sfade .8s 1.5s ease forwards}
@keyframes draw{to{stroke-dashoffset:0}}
@keyframes spark{0%{stroke-dashoffset:105;opacity:0}12%{opacity:1}86%{opacity:1}100%{stroke-dashoffset:5;opacity:0}}
@keyframes sfade{from{opacity:0}to{opacity:1}}
@keyframes srise{from{opacity:0;transform:translateY(7px)}to{opacity:1;transform:translateY(0)}}
@media(prefers-reduced-motion:reduce){
  .splash-logo g path{animation:none;stroke-dashoffset:0}
  .splash-logo .spark{display:none}
  .splash-inner,.splash-words .sw,.splash-bar{animation:none;opacity:1}
  .splash-words .sw{transform:none}
  .splash-logo circle{opacity:1}
}
/* ===== Overlay de generation (logo + 3 mots comme etapes) ===== */
.genov{position:fixed;inset:0;z-index:90;opacity:0;transition:opacity .4s ease;
  background:radial-gradient(circle at 50% 40%, #141519 0%, #0a0a0b 74%);
  display:flex;align-items:center;justify-content:center}
.genov.on{opacity:1}
.genov[hidden]{display:none}
.genov-inner{display:flex;flex-direction:column;align-items:center;gap:28px;width:min(90vw,420px)}
.genov-logo{width:96px;height:120px;animation:genglow 2.2s ease-in-out infinite}
.genov-logo svg{width:100%;height:100%}
.genov-steps{display:flex;flex-direction:column;gap:12px;align-items:flex-start}
.gstep{display:flex;align-items:center;gap:15px;font-family:var(--font-display);font-weight:800;
  text-transform:uppercase;letter-spacing:.06em;font-size:clamp(26px,6.5vw,36px);line-height:1;
  color:var(--muted);opacity:.4;transition:opacity .35s ease,color .35s ease}
.gstep .gdot{width:18px;height:18px;border-radius:50%;border:2px solid var(--muted);flex-shrink:0;
  display:grid;place-items:center;font-size:12px;line-height:1;transition:all .3s ease}
.gstep.active{opacity:1;color:var(--orange)}
.gstep.active .gdot{border-color:var(--orange);animation:gdotpulse 1.1s ease-in-out infinite}
.gstep.done{opacity:1;color:var(--text)}
.gstep.done .gdot{border-color:var(--green);background:var(--green);color:#fff}
.gstep.done .gdot::after{content:'✓'}
.genov-hint{font-family:var(--font-body);font-size:14px;color:var(--muted);min-height:20px;text-align:center}
@keyframes genglow{0%,100%{filter:drop-shadow(0 0 6px rgba(255,107,53,.35))}
  50%{filter:drop-shadow(0 0 16px rgba(255,107,53,.7))}}
@keyframes gdotpulse{0%,100%{box-shadow:0 0 0 0 rgba(255,107,53,.5)}50%{box-shadow:0 0 0 7px rgba(255,107,53,0)}}
@media(prefers-reduced-motion:reduce){ .genov-logo,.gstep.active .gdot{animation:none} }
.tb-brand{display:none;align-items:center;gap:8px}
.tb-brand .tb-logo{width:24px;height:30px;display:grid;place-items:center;flex-shrink:0}
.tb-brand b{font-family:var(--font-display);text-transform:uppercase;letter-spacing:.05em;font-size:16px}
.mnav{display:none}
.content{padding:22px 24px;flex:1}
.section{display:none}.section.active{display:block}
/* KPI */
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(178px,1fr));gap:14px;margin-bottom:22px}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:var(--radius);padding:17px 18px;
  box-shadow:var(--shadow);transition:transform .2s var(--ease),border-color .2s var(--ease),box-shadow .2s var(--ease)}
.kpi:hover{transform:translateY(-2px);border-color:color-mix(in srgb,var(--orange) 35%,var(--line));box-shadow:var(--shadow-lift)}
.kpi .label{font-size:10.5px;color:var(--muted);text-transform:uppercase;letter-spacing:.1em;font-weight:600;
  min-height:26px;display:flex;align-items:flex-start}
.kpi .val{font-family:var(--font-display);font-size:32px;font-weight:800;margin-top:6px;
  letter-spacing:-.01em;font-variant-numeric:tabular-nums;line-height:1}
.kpi .delta{font-size:12px;margin-top:5px;font-variant-numeric:tabular-nums}
.delta.good{color:var(--green)}.delta.bad{color:var(--red)}
/* Toolbar */
.toolbar{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-bottom:14px}
.toolbar input,.toolbar select{padding:9px 12px;border:1px solid var(--line);border-radius:9px;
  background:var(--card);color:var(--text);font-size:13px}
.toolbar input[type=search]{min-width:230px}
.chips{display:flex;gap:6px;flex-wrap:wrap}
.chip{all:unset;cursor:pointer;padding:7px 14px;border-radius:20px;border:1px solid var(--line);
  font-family:var(--font-body);font-weight:550;letter-spacing:.005em;
  font-size:12.5px;color:var(--muted);background:transparent;white-space:nowrap;
  transition:border-color .16s var(--ease),color .16s var(--ease),background .16s var(--ease)}
.chip:hover{border-color:color-mix(in srgb,var(--orange) 55%,var(--line));color:var(--text)}
.chip.on{background:var(--orange-soft);color:var(--orange);border-color:var(--orange)}
.btn{all:unset;cursor:pointer;padding:10px 15px;border-radius:var(--radius-sm);background:var(--orange);color:#fff;
  font-weight:600;font-size:13px;transition:transform .12s var(--ease),background .16s var(--ease),box-shadow .16s var(--ease)}
.btn:hover{background:var(--orange-dark);box-shadow:0 4px 14px -4px rgba(255,107,53,.5)}
.btn:active{transform:scale(.975)}
.btn.ghost{background:transparent;border:1px solid var(--line);color:var(--text);box-shadow:none}
.btn.ghost:hover{border-color:var(--orange);background:transparent}
.ico-btn{display:inline-flex;align-items:center;gap:8px}
.ico-btn .ic{width:16px;height:16px}
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
.panel{background:var(--card);border:1px solid var(--line);border-radius:12px;box-shadow:var(--shadow);min-width:0}
.panel h3{font-family:var(--font-display);font-size:13px;font-weight:700;text-transform:uppercase;
  letter-spacing:.06em;padding:14px 16px;border-bottom:1px solid var(--line);display:flex;gap:8px;align-items:center}
.panel .badge{margin-left:auto;font-size:12px;color:var(--muted)}
.empty{padding:26px;text-align:center;color:var(--muted);font-size:13px}
.note{font-size:12px;color:var(--muted);margin:10px 2px}
.mnav button{all:unset;cursor:pointer;display:inline-flex;align-items:center;gap:7px;padding:8px 13px;border-radius:9px;white-space:nowrap;
  font-family:var(--font-body);font-weight:550;letter-spacing:.005em;
  font-size:13px;color:var(--muted);border:1px solid var(--line);transition:all .16s var(--ease)}
.mnav button .ico .ic{width:16px;height:16px}
.mnav button.active{background:var(--orange-soft);color:var(--orange);border-color:var(--orange)}
/* Cartes de transfert (affichage mobile) — masquees par defaut (desktop = tableau) */
.tcards{display:none;flex-direction:column;gap:12px}
.tcard{background:var(--card);border:1px solid var(--line);border-radius:var(--radius);padding:14px;box-shadow:var(--shadow);
  transition:border-color .18s var(--ease),transform .18s var(--ease)}
.tcard:hover{border-color:color-mix(in srgb,var(--orange) 30%,var(--line))}
.tcard .top{display:flex;align-items:center;gap:10px;margin-bottom:9px}
.tcard .score{margin-left:auto;font-family:var(--font-display);font-weight:800;
  font-variant-numeric:tabular-nums;font-size:19px;letter-spacing:.02em}
.tcard .score small{font-size:10px;color:var(--muted);font-weight:600;letter-spacing:.06em;margin-right:3px}
.tcard .flux{font-family:var(--font-display);font-weight:800;text-transform:uppercase;
  letter-spacing:.02em;font-size:16px;line-height:1.15;margin-bottom:8px}
.tcard .flux .arrow{color:var(--orange);margin:0 7px}
.tcard .meta{display:flex;flex-wrap:wrap;gap:5px 16px;font-size:13.5px;margin-bottom:7px}
.tcard .meta .k{color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.05em;margin-right:4px}
.tcard .dispo{font-size:13px;margin-bottom:7px;font-variant-numeric:tabular-nums}
.tcard .dispo .k{color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.05em;margin-right:4px}
.tcard .motif{font-size:12.5px;color:var(--muted);margin-bottom:13px;line-height:1.4}
.dsug{margin:10px 0 4px;padding:10px 12px;background:var(--green-bg);border:1px solid var(--line);border-radius:11px}
.dsug-h{font-size:11.5px;font-weight:700;color:var(--green);text-transform:uppercase;letter-spacing:.03em;margin-bottom:7px}
.dsug-row{display:flex;flex-wrap:wrap;gap:8px;align-items:center;font-size:12.5px;padding:3px 0}
.dsug-mag{font-weight:700}
.dsug-t{background:var(--chip);border-radius:6px;padding:1px 7px;font-weight:600}
.dsug-q{color:var(--green);font-weight:600}
.dsug-c{color:var(--muted)}
.valo-h{display:flex;align-items:center;gap:9px;font-family:var(--font-display);font-weight:800;
  font-size:15px;letter-spacing:-.01em;margin:22px 2px 12px}
.valo-h:first-child{margin-top:4px}
.valo-h .ico .ic{width:18px;height:18px}
.valo-h .ico{color:var(--orange)}
.vrow{display:flex;align-items:center;gap:12px;flex-wrap:wrap;background:var(--card);border:1px solid var(--line);
  border-radius:var(--radius-sm);padding:12px 14px}
.vrow .vmag{font-weight:700;min-width:120px}
.vrow .vmeta{color:var(--muted);font-size:12.5px;font-variant-numeric:tabular-nums}
.vrow .vca{margin-left:auto;font-family:var(--font-display);font-weight:800;font-size:17px;
  font-variant-numeric:tabular-nums;color:var(--green)}
.vrow .vmarge{color:var(--muted);font-size:12.5px;font-variant-numeric:tabular-nums;min-width:110px;text-align:right}
.vchips{display:flex;flex-wrap:wrap;gap:8px;margin-top:10px}
.vchip{background:var(--card2);border:1px solid var(--line);border-radius:20px;padding:6px 12px;font-size:12.5px;font-weight:600}
.valo-hero{background:linear-gradient(135deg,var(--orange-soft),transparent 70%),var(--card);
  border:1px solid color-mix(in srgb,var(--orange) 30%,var(--line));border-radius:16px;padding:22px 24px;margin-bottom:6px}
.valo-hero .vh-label{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.12em;font-weight:600}
.valo-hero .vh-val{font-family:var(--font-display);font-weight:800;font-size:44px;line-height:1;letter-spacing:-.02em;
  color:var(--orange);margin-top:8px;font-variant-numeric:tabular-nums}
.valo-hero .vh-sub{font-size:13px;color:var(--muted);margin-top:8px;font-variant-numeric:tabular-nums}
.valo-hero .vh-sub b{color:var(--text)}
.valo-h.vh-first{margin-top:20px}
.tcard .acts{display:flex;gap:10px}
.tcard .acts button{flex:1;min-height:48px;border-radius:12px;border:1px solid var(--line);
  background:var(--card2);color:var(--text);font-family:var(--font-display);font-weight:700;
  text-transform:uppercase;letter-spacing:.04em;font-size:13.5px;cursor:pointer;
  display:flex;align-items:center;justify-content:center;gap:7px}
.tcard .acts button.ok.on{background:var(--green);color:#fff;border-color:var(--green)}
.tcard .acts button.no.on{background:var(--red);color:#fff;border-color:var(--red)}
.tcard.reviewed-ok{border-color:var(--green)}
.tcard.reviewed-no{opacity:.5}
/* Barre de navigation basse (mobile) facon appli */
.botnav{display:none}
@media(max-width:820px){
  .sidebar{display:none}
  .grid2{grid-template-columns:1fr}
  .tb-brand{display:flex}
  .topbar h1{font-size:15px}
  .topbar .sub{display:none}
  .motto{display:none}
  .mnav{display:flex;gap:7px;overflow-x:auto;padding:10px 16px;background:var(--card);
    border-bottom:1px solid var(--line);position:sticky;top:57px;z-index:4}
  .content{padding:16px}
}
@media(max-width:640px){
  /* nav basse a la place des onglets du haut */
  .mnav{display:none}
  .botnav{display:flex;position:fixed;left:0;right:0;bottom:0;z-index:20;background:var(--sidebar-bg);
    border-top:1px solid #ffffff1c;padding:5px 4px calc(5px + env(safe-area-inset-bottom))}
  .botnav button{all:unset;flex:1;display:flex;flex-direction:column;align-items:center;gap:4px;
    padding:7px 2px;color:var(--sidebar-text);font-size:10px;font-weight:600;
    letter-spacing:.01em;cursor:pointer;text-align:center;font-family:var(--font-body);
    transition:color .16s var(--ease)}
  .botnav button .ico .ic{width:23px;height:23px}
  .botnav button.active{color:var(--orange)}
  .content{padding:14px 13px calc(72px + env(safe-area-inset-bottom))}
  /* transferts + magasin : cartes au lieu du tableau */
  .tbl-only{display:none}
  .tcards.card-only{display:flex}
  .mvlist.card-only{display:flex}
  /* KPI en 2 colonnes compactes */
  .kpis{grid-template-columns:1fr 1fr;gap:10px;margin-bottom:16px}
  .kpi{padding:13px}
  .kpi .val{font-size:23px}
  /* barre d'outils empilee, pleine largeur, cibles tactiles */
  .toolbar{gap:9px}
  .toolbar input[type=search]{flex:1 0 100%;min-width:0;width:100%;padding:12px 13px;font-size:15px}
  .toolbar .chips{flex:1 0 100%;flex-wrap:nowrap;overflow-x:auto;-webkit-overflow-scrolling:touch;padding-bottom:2px}
  .toolbar select{flex:1;min-width:0;padding:11px 12px;font-size:14px}
  .toolbar .spacer{display:none}
  .toolbar .btn{flex:1 0 100%;display:block;width:100%;text-align:center;padding:13px;font-size:14px;box-sizing:border-box}
  /* topbar : titre masque (la nav basse indique la section) ; slogan defilant */
  .topbar{padding:11px 15px;gap:10px}
  .topbar h1{display:none}
  .theme-btn{padding:7px 10px}
  .theme-btn .tlbl{display:none}
  .motto{display:block;position:relative;width:120px;height:22px;gap:0;font-size:14px;letter-spacing:.06em}
  .motto span{position:absolute;right:0;top:0;opacity:0;animation:mottocycle 6s infinite}
  .motto .w1{animation-delay:0s}
  .motto .w2{animation-delay:2s}
  .motto .w3{animation-delay:4s}
}
@keyframes mottocycle{
  0%{opacity:0;transform:translateY(6px)}
  5%{opacity:1;transform:translateY(0)}
  29%{opacity:1;transform:translateY(0)}
  34%{opacity:0;transform:translateY(-6px)}
  100%{opacity:0;transform:translateY(-6px)}
}
</style>
</head>
<body>
<div id="splash">
  <div class="splash-inner">
    <div class="splash-logo"><svg viewBox="0 0 64 80" fill="none" aria-hidden="true"><defs><linearGradient id="fkgS" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#FF9E6D"/><stop offset="1" stop-color="#EF5A2A"/></linearGradient></defs><g stroke="url(#fkgS)" stroke-linecap="round" fill="none"><path d="M44 16C44 8 24 7 22 20C20 33 42 34 40 48C38 63 19 62 16 54" stroke-width="3.5" opacity=".45" transform="translate(-5 0)"/><path d="M46 16C46 8 24 6 22 20C20 33 44 34 42 48C40 64 18 62 16 54" stroke-width="5"/><path d="M48 16C48 8 26 7 24 20C22 33 46 34 44 48C42 63 21 62 18 54" stroke-width="3.5" opacity=".7" transform="translate(5 0)"/></g><path class="spark" pathLength="100" d="M46 16C46 8 24 6 22 20C20 33 44 34 42 48C40 64 18 62 16 54" stroke="#fff" stroke-width="5.5" stroke-linecap="round" fill="none"/><circle cx="46" cy="16" r="2.4" fill="#FF9E6D"/><circle cx="16" cy="54" r="2.4" fill="#EF5A2A"/></svg></div>
    <div class="splash-words"><span class="sw sw1">ANALYSE.</span><span class="sw sw2">OPTIMISE.</span><span class="sw sw3">GAGNE.</span></div>
    <div class="splash-bar"></div>
  </div>
</div>
<div id="genov" class="genov" hidden>
  <div class="genov-inner">
    <div class="genov-logo"><svg viewBox="0 0 64 80" fill="none" aria-hidden="true"><defs><linearGradient id="fkgG" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#FF9E6D"/><stop offset="1" stop-color="#EF5A2A"/></linearGradient></defs><g stroke="url(#fkgG)" stroke-linecap="round" fill="none"><path d="M44 16C44 8 24 7 22 20C20 33 42 34 40 48C38 63 19 62 16 54" stroke-width="3.5" opacity=".45" transform="translate(-5 0)"/><path d="M46 16C46 8 24 6 22 20C20 33 44 34 42 48C40 64 18 62 16 54" stroke-width="5"/><path d="M48 16C48 8 26 7 24 20C22 33 46 34 44 48C42 63 21 62 18 54" stroke-width="3.5" opacity=".7" transform="translate(5 0)"/></g><circle cx="46" cy="16" r="2.4" fill="#FF9E6D"/><circle cx="16" cy="54" r="2.4" fill="#EF5A2A"/></svg></div>
    <div class="genov-steps">
      <div class="gstep" data-step="analyse"><span class="gdot"></span>ANALYSE.</div>
      <div class="gstep" data-step="optimise"><span class="gdot"></span>OPTIMISE.</div>
      <div class="gstep" data-step="gagne"><span class="gdot"></span>GAGNE.</div>
    </div>
    <div class="genov-hint" id="genovHint"></div>
  </div>
</div>
<aside class="sidebar">
  <div class="brand"><div class="logo"><svg class="fklogo" viewBox="0 0 64 80" fill="none" aria-hidden="true"><defs><linearGradient id="fkgA" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#FF9E6D"/><stop offset="1" stop-color="#EF5A2A"/></linearGradient></defs><g stroke="url(#fkgA)" stroke-linecap="round" fill="none"><path d="M44 16C44 8 24 7 22 20C20 33 42 34 40 48C38 63 19 62 16 54" stroke-width="3.5" opacity=".45" transform="translate(-5 0)"/><path d="M46 16C46 8 24 6 22 20C20 33 44 34 42 48C40 64 18 62 16 54" stroke-width="5"/><path d="M48 16C48 8 26 7 24 20C22 33 46 34 44 48C42 63 21 62 18 54" stroke-width="3.5" opacity=".7" transform="translate(5 0)"/></g><circle cx="46" cy="16" r="2.4" fill="#FF9E6D"/><circle cx="16" cy="54" r="2.4" fill="#EF5A2A"/></svg></div><div><b>StockFlow AI</b><span>Recommandations</span></div></div>
  <nav class="nav" id="nav"></nav>
  <div class="side-foot" id="foot"></div>
</aside>
<div class="main">
  <div class="topbar">
    <div class="tb-brand"><span class="tb-logo"><svg class="fklogo" viewBox="0 0 64 80" fill="none" aria-hidden="true"><defs><linearGradient id="fkgB" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#FF9E6D"/><stop offset="1" stop-color="#EF5A2A"/></linearGradient></defs><g stroke="url(#fkgB)" stroke-linecap="round" fill="none"><path d="M44 16C44 8 24 7 22 20C20 33 42 34 40 48C38 63 19 62 16 54" stroke-width="3.5" opacity=".45" transform="translate(-5 0)"/><path d="M46 16C46 8 24 6 22 20C20 33 44 34 42 48C40 64 18 62 16 54" stroke-width="5"/><path d="M48 16C48 8 26 7 24 20C22 33 46 34 44 48C42 63 21 62 18 54" stroke-width="3.5" opacity=".7" transform="translate(5 0)"/></g><circle cx="46" cy="16" r="2.4" fill="#FF9E6D"/><circle cx="16" cy="54" r="2.4" fill="#EF5A2A"/></svg></span><b id="tbBrand"></b></div>
    <div><h1 id="ttl">Transferts recommandes</h1><div class="sub" id="sub"></div></div>
    <div class="spacer"></div>
    <div class="motto" aria-hidden="true"><span class="w1">ANALYSE.</span><span class="w2">OPTIMISE.</span><span class="w3">GAGNE.</span></div>
    <button class="theme-btn" id="theme">◐<span class="tlbl"> Thème</span></button>
    <button class="theme-btn" id="logout" title="Se déconnecter" style="display:none">⏻<span class="tlbl"> Quitter</span></button>
  </div>
  <nav class="mnav" id="mnav"></nav>
  <div class="content" id="content"></div>
</div>
<nav class="botnav" id="botnav"></nav>
<script id="data" type="application/json">/*__DATA__*/</script>
<script>
// DATA et la persistance de revue sont fournis par le "shell" (prototype ou
// Supabase). Par defaut : donnees inlinees + revue en localStorage.
// Intro (splash electrique) : disparait apres ~2,4 s, ou au clic/tap
(function(){ const s=document.getElementById('splash'); if(!s) return;
  const go=()=>{ if(!s.classList.contains('out')){ s.classList.add('out'); setTimeout(()=>{ if(s&&s.parentNode) s.remove(); }, 550); } };
  s.addEventListener('click', go); setTimeout(go, 2500);
})();

let DATA = null, C = {}, reviews = {}, shipments = {};
window.bootData = window.bootData || (async () =>
  JSON.parse(document.getElementById('data').textContent));
window.ReviewStore = window.ReviewStore || {
  async load(){ try{return JSON.parse(localStorage.getItem('sf_'+(DATA.meta.runid||'run'))||'{}')}catch(e){return {}} },
  async set(n,val){ localStorage.setItem('sf_'+(DATA.meta.runid||'run'), JSON.stringify(reviews)); }
};
const fmt = n => (typeof n==='number'? n.toLocaleString('fr-FR'):n);
const fmtEur = n => (typeof n==='number'? Math.round(n).toLocaleString('fr-FR'):n)+' €';
function impactBlock(imp){
  if(!imp || !(imp.units>0))
    return `<div class="note">💡 Impact des transferts : il sera mesuré à la prochaine génération (avec les ventes de la semaine suivante).</div>`;
  const card=(l,v)=>`<div class="kpi"><div class="label">${l}</div><div class="val">${v}</div></div>`;
  return `<div class="note">💰 Ventes réalisées sur les références transférées (semaine suivante, chez le destinataire) — estimation.</div>
    <div class="kpis" style="margin-bottom:22px">
      ${card('Articles vendus', fmt(imp.units))}
      ${card('CA généré', fmtEur(imp.ca))}
      ${card('Marge générée', fmtEur(imp.marge))}
    </div>`;
}
const pcls = p => 'p-'+String(p).replace(/[^A-Za-z]/g,'').slice(0,10).replace('Fortementrecommande','Fortement').replace('Avalider','Avalider');

const TABS = [
  {id:'transferts',ico:'box',label:'Transferts',short:'Transf.'},
  {id:'magasin',ico:'store',label:'Par magasin',short:'Magasin'},
  {id:'flux',ico:'shuffle',label:'Synthèse flux',short:'Flux'},
  {id:'simulation',ico:'chart',label:'Stats',short:'Stats'},
  {id:'cas',ico:'warning',label:'Cas non traités',short:'Cas'},
  {id:'differences',ico:'flag',label:'Différences',short:'Diff.'},
  {id:'demandes',ico:'bell',label:'Demandes urgentes',short:'Demandes'},
  {id:'reassort',ico:'warehouse',label:'Réassort central',short:'Réassort'},
  {id:'valorisation',ico:'trend',label:'Valorisation',short:'Valeur'},
  {id:'users',ico:'user',label:'Utilisateurs',short:'Users'},
  {id:'generer',ico:'sparkle',label:'Générer',short:'Générer'},
];
let tab='transferts';
// Role & vue magasin (STORES = magasins accessibles ; STORE = celui affiche)
let MODE='admin', STORE=null, STORES=[], PREVIEW=false, stab='expedier', openDest=null;
let RUNS_CACHE=null;   // historique des runs (admin)
const F={q:'',prio:'',boutique:'',etat:''};

// Jeu d'icones trait (Phosphor-like, monochrome, currentColor) — remplace les emojis.
const ICONS={
  box:'<path d="M3.5 7.5 12 3l8.5 4.5v9L12 21l-8.5-4.5z"/><path d="M3.5 7.5 12 12l8.5-4.5"/><path d="M12 12v9"/>',
  store:'<path d="M4 9.6V20h16V9.6"/><path d="M3.2 9.4 4.6 4h14.8l1.4 5.4a2.9 2.9 0 0 1-5.8 0 2.9 2.9 0 0 1-5.8 0 2.9 2.9 0 0 1-5.8 0Z"/><path d="M9.5 20v-4.5h5V20"/>',
  shuffle:'<path d="M4 8h3.5l9 8H20"/><path d="M4 16h3.5l9-8H20"/><path d="m16.5 5 3.5 3-3.5 3"/><path d="m16.5 13 3.5 3-3.5 3"/>',
  chart:'<path d="M5 4v16.5h15"/><path d="M9 20V14"/><path d="M13.5 20V9.5"/><path d="M18 20v-4"/>',
  warning:'<path d="M12 4.2 2.6 20h18.8z"/><path d="M12 10v4.5"/><path d="M12 17.6h.01"/>',
  flag:'<path d="M5.5 21V4"/><path d="M5.5 4.5h11l-2.2 3.2 2.2 3.2h-11"/>',
  bell:'<path d="M6 9.5a6 6 0 0 1 12 0c0 4.5 1.8 5.7 1.8 5.7H4.2S6 14 6 9.5"/><path d="M10 20a2 2 0 0 0 4 0"/>',
  warehouse:'<path d="M3 21V8l9-4 9 4v13"/><path d="M2.5 21h19"/><path d="M8 21v-6.5h8V21"/><path d="M8 14.5h8"/>',
  user:'<circle cx="12" cy="8" r="3.4"/><path d="M5.2 20c0-3.5 3-6 6.8-6s6.8 2.5 6.8 6"/>',
  sparkle:'<path d="M12 3.2l1.9 5.4 5.4 1.9-5.4 1.9L12 17.8l-1.9-5.4L4.7 10.5l5.4-1.9z"/><path d="M18.5 15.5l.7 2 2 .7-2 .7-.7 2-.7-2-2-.7 2-.7z"/>',
  upload:'<path d="M12 15.5V4"/><path d="m7.5 8.5 4.5-4.5 4.5 4.5"/><path d="M4.5 15v4a1.2 1.2 0 0 0 1.2 1.2h12.6A1.2 1.2 0 0 0 19.5 19v-4"/>',
  download:'<path d="M12 4v11.5"/><path d="m7.5 11 4.5 4.5 4.5-4.5"/><path d="M4.5 15v4a1.2 1.2 0 0 0 1.2 1.2h12.6A1.2 1.2 0 0 0 19.5 19v-4"/>',
  grid:'<rect x="4" y="4" width="7" height="7" rx="1.4"/><rect x="13" y="4" width="7" height="7" rx="1.4"/><rect x="4" y="13" width="7" height="7" rx="1.4"/><rect x="13" y="13" width="7" height="7" rx="1.4"/>',
  bolt:'<path d="M13 3 4.5 13.5H11l-1 7.5 8.5-11H12z"/>',
  trend:'<path d="M4 15.5 10 9.5l3.2 3.2L20 6"/><path d="M16 6h4v4"/>',
};
function icon(n){ return '<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'+(ICONS[n]||'')+'</svg>'; }

function nav(){
  document.getElementById('nav').innerHTML = TABS.map(t=>`
    <button data-tab="${t.id}" class="${t.id===tab?'active':''}">
      <span class="ico">${icon(t.ico)}</span>${t.label}
      ${t.id==='transferts'?`<span class="count">${DATA.transfers.length}</span>`:''}
    </button>`).join('');
  document.getElementById('mnav').innerHTML = TABS.map(t=>`
    <button data-tab="${t.id}" class="${t.id===tab?'active':''}"><span class="ico">${icon(t.ico)}</span>${t.label}</button>`).join('');
  document.getElementById('botnav').innerHTML = TABS.map(t=>`
    <button data-tab="${t.id}" class="${t.id===tab?'active':''}"><span class="ico">${icon(t.ico)}</span>${t.short||t.label}</button>`).join('');
  document.querySelectorAll('#nav button, #mnav button, #botnav button').forEach(b=>b.onclick=()=>{tab=b.dataset.tab;render();
    window.scrollTo({top:0});});
  const runOpts=(RUNS_CACHE||[]).map((r,i)=>{
    const sel=(window.__runId ? r.id===window.__runId : i===0) ? ' selected':'';
    return `<option value="${r.id}"${sel}>${String(r.date_execution||r.created_at||'').slice(0,10)} · ${r.nb_transferts} transf.${i===0?' (actuel)':''}</option>`;
  }).join('');
  document.getElementById('foot').innerHTML =
    `Perimetre : ${DATA.meta.perimetre||'-'}<br>Cible ${DATA.meta.cible||'-'} j · ${DATA.meta.date||''}`
    + `<select class="foot-sel" id="previewStore"><option value="">Prévisualiser un magasin…</option>`
    + boutiques().map(b=>`<option>${b}</option>`).join('') + `</select>`
    + ((RUNS_CACHE&&RUNS_CACHE.length>1) ? `<select class="foot-sel" id="runSel">${runOpts}</select>` : '');
}

function reviewSummary(){
  const el=document.getElementById('revsum'); if(!el) return;   // present uniquement dans l'onglet Transferts
  let ok=0,no=0; Object.values(reviews).forEach(v=>{if(v==='ok')ok++;else if(v==='no')no++;});
  const tot=DATA.transfers.length;
  el.innerHTML =
    `<span><b style="color:var(--green)">${ok}</b> validés</span><span><b style="color:var(--red)">${no}</b> refusés</span><span><b>${tot-ok-no}</b> à revoir</span>`;
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

// Carte de transfert (affichage mobile) — memes donnees que la ligne de tableau
function transfersCard(r){
  const st=reviews[r[C.n]]||'todo';
  const cls=st==='ok'?'reviewed-ok':st==='no'?'reviewed-no':'';
  return `<div class="tcard ${cls}" data-n="${r[C.n]}">
    <div class="top"><span class="pill ${pcls(r[C.prio])}">${r[C.prio]}</span>
      <span class="score"><small>SCORE</small>${r[C.score]}</span></div>
    <div class="flux">${r[C.exp]}<span class="arrow">→</span>${r[C.dest]}</div>
    <div class="meta">
      <span><span class="k">Réf</span>${r[C.ref]}</span>
      <span><span class="k">Taille</span>${r[C.taille]}</span>
      <span><span class="k">Qté</span>${r[C.qte]}</span>
      <span><span class="k">Couv</span>${r[C.covA]}→${r[C.covB]} j</span>
      ${r[C.marque]?`<span><span class="k">Marque</span>${r[C.marque]}</span>`:''}
    </div>
    <div class="dispo"><span class="k">Dispo finale</span>${r[C.dispoB]||'—'}</div>
    ${r[C.motif]?`<div class="motif">${r[C.motif]}</div>`:''}
    <div class="rev acts">
      <button class="ok ${st==='ok'?'on':''}" data-a="ok">✓ Valider</button>
      <button class="no ${st==='no'?'on':''}" data-a="no">✕ Refuser</button>
    </div></div>`;
}

// Liste des transferts : tableau (desktop) + cartes (mobile), bascule en CSS
function listHTML(rows){
  return `<div class="tablewrap tbl-only"><table><thead><tr>
    <th class="num">N°</th><th>Priorité</th><th class="num">Score</th><th>Marque</th>
    <th>Flux</th><th>Réf. (code-barre)</th><th>Taille</th><th class="num">Qté</th>
    <th class="num">Couv. dest.</th><th>Dispo finale (dest.)</th><th>Motif</th><th>Revue</th>
  </tr></thead><tbody>${rows.slice(0,1200).map(transfersRow).join('')}</tbody></table></div>
  <div class="tcards card-only">${rows.slice(0,400).map(transfersCard).join('')}
    ${rows.length>400?`<div class="note">Affichage limité à 400 cartes — affinez les filtres.</div>`:''}
  </div>`;
}

function bindReview(root){
  root.querySelectorAll('[data-n] .rev button').forEach(b=>{
    b.onclick=()=>{ const host=b.closest('[data-n]'); const n=host.dataset.n; const a=b.dataset.a;
      reviews[n]= reviews[n]===a? undefined : a; if(!reviews[n]) delete reviews[n];
      window.ReviewStore.set(n, reviews[n]); const st=reviews[n]||'todo';
      // synchronise les 2 rendus (ligne + carte) partageant ce data-n
      document.querySelectorAll('[data-n="'+n+'"]').forEach(el=>{
        el.classList.remove('reviewed-ok','reviewed-no');
        if(st!=='todo') el.classList.add(st==='ok'?'reviewed-ok':'reviewed-no');
        el.querySelectorAll('.rev button').forEach(x=>x.classList.toggle('on', reviews[n]===x.dataset.a));
      });
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
    <button class="btn ico-btn" id="exp">${icon('download')}Exporter les validés (CSV)</button>
  </div>
  <div class="revsum" id="revsum"></div>
  <div class="note">${rows.length} transfert(s) affiché(s) sur ${DATA.transfers.length}. Cliquez ✓ / ✕ pour valider ou refuser — la revue est enregistrée.</div>
  <div id="tlist">${listHTML(rows)}</div>
  ${rows.length>1200?`<div class="note">Tableau limité à 1200 lignes — affinez les filtres pour voir le reste.</div>`:''}`;
}

function renderMagasin(){
  const bs=boutiques();
  const sel=F.boutique||bs[0];
  const opts=bs.map(b=>`<option ${b===sel?'selected':''}>${b}</option>`).join('');
  const recoit=DATA.transfers.filter(r=>r[C.dest]===sel);
  const envoie=DATA.transfers.filter(r=>r[C.exp]===sel);
  const mvCard=(r,who)=>`<div class="mvcard">
      <div class="mvtop"><span class="mvstore">${who==='Depuis'?r[C.exp]:r[C.dest]}</span>
        <span class="mvqte">${r[C.qte]} <small>pièces</small></span></div>
      <div class="mvmeta">${r[C.ref]} · Taille <b>${r[C.taille]}</b> · score ${r[C.score]}</div>
      ${r[C.dispoB]?`<div class="mvdispo">Dispo finale : ${r[C.dispoB]}</div>`:''}</div>`;
  const mini=(arr,who)=>arr.length? `<div class="tablewrap tbl-only"><table><thead><tr>
      <th>${who}</th><th>Réf.</th><th>Taille</th><th class="num">Qté</th><th class="num">Score</th><th>Dispo finale</th>
    </tr></thead><tbody>${arr.slice(0,400).map(r=>`<tr>
      <td class="flow">${who==='Depuis'?r[C.exp]:r[C.dest]}</td><td>${r[C.ref]}</td><td>${r[C.taille]}</td>
      <td class="num">${r[C.qte]}</td><td class="num">${r[C.score]}</td><td class="dispo">${r[C.dispoB]}</td>
    </tr>`).join('')}</tbody></table></div>
    <div class="mvlist card-only">${arr.slice(0,400).map(r=>mvCard(r,who)).join('')}</div>`
    : `<div class="empty">Aucun mouvement.</div>`;
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
  const labels={stock_total:'Stock total',valeur_stock:'Valeur du stock — prix d\'achat (€)',stock_dormant:'Stock dormant',
    ruptures:'Ruptures',refs_sous_7j:'Réf. sous 7 j',refs_sous_14j:'Réf. sous 14 j',
    couverture_moyenne:'Couverture moyenne (j)',grilles_coherentes:'Grilles cohérentes',
    tailles_coeur_dispo:'Tailles cœur disponibles',score_sante_reseau:'Score santé réseau',
    nb_transferts:'Nb transferts',nb_destinations:'Nb destinations',valeur_stock_deplace:'Valeur déplacée (€)'};
  const rows=Object.entries(DATA.kpis).map(([k,v])=>{
    const d=(v.apres-v.avant); const good=/rupture|dormant|sous_/.test(k)? d<=0 : d>=0;
    return `<tr><td>${labels[k]||k}</td><td class="num">${fmt(v.avant)}</td><td class="num">${fmt(v.apres)}</td>
      <td class="num" style="color:${d===0?'var(--muted)':good?'var(--green)':'var(--red)'}">${d>0?'+':''}${fmt(+d.toFixed(1))}</td></tr>`;
  }).join('');
  return impactBlock(DATA.meta.impact)+kpiStrip()+`<div class="tablewrap"><table><thead><tr><th>Indicateur</th>
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
  const ps=document.getElementById('previewStore');
  if(ps) ps.onchange=e=>{ if(e.target.value){ STORE=e.target.value; PREVIEW=true; MODE='store'; stab='expedier'; renderStore(); } };
  const rs=document.getElementById('runSel');
  if(rs) rs.onchange=e=>{ window.__runId=e.target.value||null; window.boot(); };
  const T=TABS.find(t=>t.id===tab);
  document.getElementById('ttl').textContent = {transferts:'Transferts recommandés',magasin:'Vue par magasin',
    flux:'Synthèse par flux',simulation:'Statistiques (avant / après)',cas:'Cas non traités',
    differences:'Différences signalées',demandes:'Demandes urgentes',
    reassort:'Réassort central (CENTRAL → magasins)',
    valorisation:'Valorisation — argent généré',
    users:'Gestion des utilisateurs',generer:'Générer une mise à jour'}[tab];
  document.getElementById('sub').textContent = DATA.meta.perimetre+' · '+DATA.transfers.length+' transferts · cible '+DATA.meta.cible+' j';
  const c=document.getElementById('content');
  c.className='content';
  c.innerHTML = {transferts:renderTransferts,magasin:renderMagasin,flux:renderFlux,
    simulation:renderSimulation,cas:renderCas,differences:renderDifferences,demandes:renderDemandes,
    reassort:renderReassort,valorisation:renderValo,users:renderUsers,generer:renderGenerer}[tab]();
  if(tab==='demandes'){ loadDemandes(); }
  if(tab==='differences'){ loadDifferences(); }
  if(tab==='reassort'){ loadReassort(c, null); }
  if(tab==='valorisation'){ loadValo(); }
  if(tab==='users'){ bindUsers(c); }
  if(tab==='generer'){ bindGenerer(c); }
  if(tab==='transferts'){
    bindReview(c); reviewSummary();
    c.querySelector('#q').oninput=e=>{F.q=e.target.value;const rows=filtered();
      const list=document.getElementById('tlist');list.innerHTML=listHTML(rows);bindReview(list);
      c.querySelector('.note').textContent=`${rows.length} transfert(s) affiché(s) sur ${DATA.transfers.length}.`;};
    c.querySelectorAll('.chip').forEach(ch=>ch.onclick=()=>{F.prio=ch.dataset.prio;render()});
    c.querySelector('#boutique').onchange=e=>{F.boutique=e.target.value;render()};
    c.querySelector('#etat').onchange=e=>{F.etat=e.target.value;render()};
    c.querySelector('#exp').onclick=exportCSV;
  }
  if(tab==='magasin'){ c.querySelector('#boutiqueM').onchange=e=>{F.boutique=e.target.value;render()}; }
}

// ============================================================
//  VUE MAGASIN (role terrain) — a expedier / receptions / grilles / urgent
// ============================================================
const STORE_TABS = [
  {id:'expedier', ico:'upload',   label:'À expédier',       short:'Expédier'},
  {id:'recevoir', ico:'download', label:'Réceptions',       short:'Récept.'},
  {id:'reassort', ico:'warehouse',label:'Réassort central', short:'Réassort'},
  {id:'grilles',  ico:'grid',     label:'Mes grilles',      short:'Grilles'},
  {id:'stats',    ico:'chart',    label:'Mes stats',        short:'Stats'},
  {id:'urgent',   ico:'bolt',     label:'Demande urgente',  short:'Urgent'},
];
function myOut(){ return DATA.transfers.filter(r=>r[C.exp]===STORE); }
function myIn(){  return DATA.transfers.filter(r=>r[C.dest]===STORE); }

function navStore(){
  const cls=id=>id===stab?'active':'';
  document.getElementById('nav').innerHTML = STORE_TABS.map(t=>`
    <button data-stab="${t.id}" class="${cls(t.id)}"><span class="ico">${icon(t.ico)}</span>${t.label}</button>`).join('');
  document.getElementById('mnav').innerHTML = STORE_TABS.map(t=>`
    <button data-stab="${t.id}" class="${cls(t.id)}"><span class="ico">${icon(t.ico)}</span>${t.label}</button>`).join('');
  document.getElementById('botnav').innerHTML = STORE_TABS.map(t=>`
    <button data-stab="${t.id}" class="${cls(t.id)}"><span class="ico">${icon(t.ico)}</span>${t.short}</button>`).join('');
  document.querySelectorAll('[data-stab]').forEach(b=>b.onclick=()=>{stab=b.dataset.stab;openDest=null;renderStore();window.scrollTo({top:0});});
  document.getElementById('foot').innerHTML = `Magasin<br><b style="color:var(--text)">${STORE}</b>`
    + (PREVIEW?`<button class="btn ghost" id="backAdmin" style="margin-top:10px;width:100%;box-sizing:border-box;text-align:center">← Vue admin</button>`:'');
}

function prioRank(p){ const s=String(p).toLowerCase();
  if(s.includes('priorit')) return 0;
  if(s.includes('fortement')) return 1;
  if(s.includes('recommand')) return 2;
  if(s.includes('valider')) return 3;
  return 4; }

// Niveau 1 : les expeditions (une carte fermee par destination, triees par prio)
function renderExpedier(){
  const rows=myOut();
  if(!rows.length) return `<div class="empty">Aucun transfert à expédier pour ${STORE}. 🎉</div>`;
  if(openDest) return renderPrepSheet(openDest);
  const byDest={}; rows.forEach(r=>{(byDest[r[C.dest]]=byDest[r[C.dest]]||[]).push(r);});
  const dests=Object.keys(byDest).map(dest=>{
    const g=byDest[dest];
    const prep=g.filter(r=>reviews[r[C.n]]==='ok').length;
    const pieces=g.reduce((s,r)=>s+(+r[C.qte]||0),0);
    const rank=Math.min.apply(null, g.map(r=>prioRank(r[C.prio])));
    const bestPrio=g.reduce((a,r)=>prioRank(r[C.prio])<prioRank(a)?r[C.prio]:a, g[0][C.prio]);
    const score=Math.max.apply(null, g.map(r=>+r[C.score]||0));
    return {dest,len:g.length,prep,pieces,rank,bestPrio,score};
  }).sort((a,b)=> a.rank-b.rank || b.score-a.score);
  const totalPrep=rows.filter(r=>reviews[r[C.n]]==='ok').length;
  const cards=dests.map(d=>{
    const pct=Math.round(d.prep/d.len*100);
    const shipped=!!shipments[shipKey(STORE,d.dest)];
    const pill = shipped
      ? `<span class="pill" style="background:var(--green-bg);color:var(--green)">✓ Expédiée</span>`
      : `<span class="pill ${pcls(d.bestPrio)}">${d.bestPrio}</span>`;
    return `<button class="destcard ${shipped?'shipped':(d.prep===d.len?'alldone':'')}" data-dest="${d.dest}">
      <div class="destcard-main">
        <div class="destcard-title">→ ${d.dest}</div>
        <div class="destcard-sub">${d.len} réf · ${d.pieces} pièces</div>
      </div>
      <div class="destcard-side">
        ${pill}
        <div class="destprogwrap"><div class="destprog"><span style="width:${pct}%"></span></div>
          <span class="destprog-txt">${d.prep}/${d.len}</span></div>
      </div>
      <span class="chev">›</span>
    </button>`;
  }).join('');
  return `<div class="prepbar"><div class="prepbar-fill" style="width:${Math.round(totalPrep/rows.length*100)}%"></div></div>
    <div class="note"><b>${totalPrep}/${rows.length}</b> transferts préparés · ouvre une expédition pour préparer</div>
    ${cards}`;
}

// Niveau 2 : le bon de prepa d'une destination (lignes minimalistes)
function renderPrepSheet(dest){
  const g=myOut().filter(r=>r[C.dest]===dest)
    .sort((a,b)=> prioRank(a[C.prio])-prioRank(b[C.prio]) || (+b[C.score]||0)-(+a[C.score]||0));
  const prep=g.filter(r=>reviews[r[C.n]]==='ok').length;
  const lines=g.map(r=>{
    const st=reviews[r[C.n]]; const cls=st==='ok'?'done':st==='diff'?'diff':'';
    return `<div class="prepline ${cls}" data-n="${r[C.n]}">
      <div class="prepinfo"><span class="prepref">${r[C.ref]}</span><span class="prepsize">${r[C.taille]}</span><span class="prepqty">×${r[C.qte]}</span></div>
      <div class="prepacts">
        <button class="pok ${st==='ok'?'on':''}" data-a="ok" title="Préparé">✓</button>
        <button class="pdiff ${st==='diff'?'on':''}" data-a="diff" title="Signaler une différence">⚠</button>
      </div></div>`;
  }).join('');
  return `<button class="prepback" id="prepBack">← Toutes les expéditions</button>
    <div class="prephead"><span class="prepdest">→ ${dest}</span><span class="prepcount">${prep}/${g.length} préparés</span></div>
    <div class="preplist">${lines}</div>
    <div id="prepfooter">${prepFooterHTML(dest, g)}</div>`;
}

function shipKey(exp,dest){ return exp+'>'+dest; }
function prepFooterHTML(dest, g){
  if(shipments[shipKey(STORE,dest)])
    return `<div class="shipdone">✓ Expédition validée <button class="shipundo" id="shipUndo">annuler</button></div>`;
  const prep=g.filter(r=>reviews[r[C.n]]==='ok').length;
  const all = g.length>0 && prep===g.length;
  return `<button class="shipbtn" id="shipBtn" ${all?'':'disabled'}>`
    + (all ? `✓ Valider l'expédition` : `Préparez tout pour valider — ${prep}/${g.length}`) + `</button>`;
}
function bindShipFooter(){
  const btn=document.getElementById('shipBtn');
  if(btn && !btn.disabled) btn.onclick=async()=>{ await window.ShipStore.validate(STORE, openDest);
    shipments[shipKey(STORE,openDest)]=true; renderStore(); window.scrollTo({top:0}); };
  const undo=document.getElementById('shipUndo');
  if(undo) undo.onclick=async()=>{ await window.ShipStore.unvalidate(STORE, openDest);
    delete shipments[shipKey(STORE,openDest)]; renderStore(); };
}

function bindExpedier(root){
  root.querySelectorAll('.destcard[data-dest]').forEach(b=>b.onclick=()=>{ openDest=b.dataset.dest; renderStore(); window.scrollTo({top:0}); });
  const bk=root.querySelector('#prepBack'); if(bk) bk.onclick=()=>{ openDest=null; renderStore(); window.scrollTo({top:0}); };
  root.querySelectorAll('.prepline [data-a]').forEach(btn=>btn.onclick=async()=>{
    const line=btn.closest('.prepline'); const n=line.dataset.n; const a=btn.dataset.a;
    reviews[n]= reviews[n]===a? undefined : a; if(!reviews[n]) delete reviews[n];
    await window.ReviewStore.set(n, reviews[n]); const st=reviews[n];
    line.classList.remove('done','diff'); if(st==='ok') line.classList.add('done'); else if(st==='diff') line.classList.add('diff');
    line.querySelectorAll('[data-a]').forEach(x=>x.classList.toggle('on', reviews[n]===x.dataset.a));
    const g=myOut().filter(r=>r[C.dest]===openDest); const prep=g.filter(r=>reviews[r[C.n]]==='ok').length;
    const el=document.querySelector('.prepcount'); if(el) el.textContent=`${prep}/${g.length} préparés`;
    const footer=document.getElementById('prepfooter'); if(footer){ footer.innerHTML=prepFooterHTML(openDest, g); bindShipFooter(); }
  });
  bindShipFooter();
}

function recCard(r){
  return `<div class="tcard">
    <div class="top"><span class="pill ${pcls(r[C.prio])}">${r[C.prio]}</span><span class="score" style="font-size:15px">de ${r[C.exp]}</span></div>
    <div class="flux">${r[C.ref]} <span style="color:var(--muted);font-weight:600">· ${r[C.taille]}</span></div>
    <div class="meta"><span><span class="k">Qté</span>${r[C.qte]}</span><span><span class="k">Couv.</span>${r[C.covA]}→${r[C.covB]} j</span>${r[C.marque]?`<span><span class="k">Marque</span>${r[C.marque]}</span>`:''}</div>
    <div class="dispo"><span class="k">Grille finale</span>${r[C.dispoB]||'—'}</div>
  </div>`;
}
function renderRecevoir(){
  const rows=myIn();
  if(!rows.length) return `<div class="empty">Aucune réception prévue pour ${STORE}.</div>`;
  const bySrc={}; rows.forEach(r=>{(bySrc[r[C.exp]]=bySrc[r[C.exp]]||[]).push(r);});
  const pcAll=rows.reduce((s,r)=>s+(+r[C.qte]||0),0);
  const groups=Object.keys(bySrc).sort().map(src=>{
    const g=bySrc[src].sort((a,b)=>b[C.score]-a[C.score]);
    const pc=g.reduce((s,r)=>s+(+r[C.qte]||0),0);
    return `<div class="panel" style="margin-bottom:14px"><h3>🚚 Depuis ${src} <span class="badge">${g.length} réf · ${pc} pièces</span></h3>
      <div class="cardcol" style="padding:12px">${g.map(recCard).join('')}</div></div>`;
  }).join('');
  return `<div class="note"><b>${rows.length}</b> réceptions à venir · <b>${pcAll}</b> pièces au total</div>${groups}`;
}

function renderGrilles(){
  const rows=myIn();
  if(!rows.length) return `<div class="empty">Aucune grille à venir.</div>`;
  const byRef={}; rows.forEach(r=>{ const ref=r[C.ref];
    if(!byRef[ref]) byRef[ref]={ref, marque:r[C.marque], dispo:r[C.dispoB], tailles:new Set(), pieces:0};
    byRef[ref].tailles.add(r[C.taille]); byRef[ref].pieces+=(+r[C.qte]||0);
    if(r[C.dispoB]) byRef[ref].dispo=r[C.dispoB]; });
  const cards=Object.values(byRef).map(g=>`<div class="tcard">
    <div class="flux">${g.ref}${g.marque?` <span style="color:var(--muted);font-weight:600">· ${g.marque}</span>`:''}</div>
    <div class="dispo" style="margin-top:8px"><span class="k">Grille finale (par taille)</span>${g.dispo||'—'}</div>
    <div class="meta"><span><span class="k">Tailles reçues</span>${[...g.tailles].join(' · ')}</span><span><span class="k">Pièces</span>${g.pieces}</span></div>
  </div>`).join('');
  return `<div class="note">Les grilles de tailles que tu auras après réception des transferts.</div><div class="cardcol">${cards}</div>`;
}

function statutPill(s){
  const m={en_attente:['En attente','amber'],validee:['Validée','green'],refusee:['Refusée','red']};
  const v=m[s]||[s,'blue'];
  return `<span class="pill" style="background:var(--${v[1]}-bg);color:var(--${v[1]})">${v[0]}</span>`;
}
function reqCard(r){
  return `<div class="tcard"><div class="top">${statutPill(r.statut)}<span class="score" style="font-size:12.5px">${(r.created_at||'').slice(0,10)}</span></div>
    <div class="flux">${r.reference}${r.taille?` <span style="color:var(--muted);font-weight:600">· ${r.taille}</span>`:''}</div>
    <div class="meta"><span><span class="k">Qté</span>${r.quantite||1}</span></div>
    ${r.motif?`<div class="motif">${r.motif}</div>`:''}</div>`;
}
function renderUrgent(){
  return `<div class="note">Demande une référence urgente : elle part à l'administrateur, qui la valide ou la refuse.</div>
    <div class="panel" style="padding:16px;margin-bottom:18px">
      <div class="ufield"><label>Référence (code-barre)</label><input id="u_ref" placeholder="ex. AR6029-008"></div>
      <div class="urow">
        <div class="ufield"><label>Taille</label><input id="u_taille" placeholder="M"></div>
        <div class="ufield"><label>Quantité</label><input id="u_qte" type="number" min="1" value="1"></div>
      </div>
      <div class="ufield"><label>Motif</label><textarea id="u_motif" rows="2" placeholder="Rupture, forte demande…"></textarea></div>
      <button class="btn" id="u_send" style="margin-top:6px">🚨 Envoyer la demande</button>
      <div class="auth-err" id="u_err" style="color:var(--red);font-size:12.5px;margin-top:10px;min-height:14px"></div>
    </div>
    <h3 style="font-family:var(--font-display);text-transform:uppercase;letter-spacing:.05em;font-size:13px;margin:6px 2px 12px">Mes demandes</h3>
    <div id="u_list" class="cardcol"><div class="empty">Chargement…</div></div>`;
}
function bindUrgent(root){
  loadMyRequests();
  root.querySelector('#u_send').onclick=async()=>{
    const err=root.querySelector('#u_err'); err.textContent='';
    const ref=root.querySelector('#u_ref').value.trim();
    const taille=root.querySelector('#u_taille').value.trim();
    const qte=parseInt(root.querySelector('#u_qte').value)||1;
    const motif=root.querySelector('#u_motif').value.trim();
    if(!ref){ err.textContent='Indique au moins une référence.'; return; }
    try{ await window.UrgentStore.create({magasin:STORE, reference:ref, taille, quantite:qte, motif});
      root.querySelector('#u_ref').value=''; root.querySelector('#u_taille').value='';
      root.querySelector('#u_motif').value=''; root.querySelector('#u_qte').value='1';
      loadMyRequests();
    }catch(e){ err.textContent='Erreur : '+(e.message||e); }
  };
}
async function loadMyRequests(){
  const list=document.getElementById('u_list'); if(!list) return;
  let reqs=[]; try{ reqs=await window.UrgentStore.listMine(STORE); }catch(e){ list.innerHTML=`<div class="empty">Erreur : ${e.message||e}</div>`; return; }
  list.innerHTML = reqs.length? reqs.map(reqCard).join('') : `<div class="empty">Aucune demande pour le moment.</div>`;
}

function renderStoreStats(){
  const out=myOut(), inn=myIn();
  const pc=a=>a.reduce((s,r)=>s+(+r[C.qte]||0),0);
  const rupt=inn.filter(r=>(+r[C.covA]||0)<7).length;
  const gains=inn.map(r=>(+r[C.covB]||0)-(+r[C.covA]||0)).filter(x=>x>0);
  const gainMoy=gains.length?(gains.reduce((s,x)=>s+x,0)/gains.length).toFixed(1):'0';
  const covA=inn.map(r=>+r[C.covB]||0).filter(x=>x>0);
  const covMoy=covA.length?(covA.reduce((s,x)=>s+x,0)/covA.length).toFixed(1):'0';
  const card=(l,v,d)=>`<div class="kpi"><div class="label">${l}</div><div class="val">${v}</div>${d?`<div class="delta">${d}</div>`:''}</div>`;
  const mi=(DATA.meta.impact&&DATA.meta.impact.par_magasin)?DATA.meta.impact.par_magasin[STORE]:null;
  const impact = (mi && mi.units>0)
    ? `<div class="note" style="margin-top:8px">💰 Ventes réalisées sur tes réceptions (semaine suivante) — estimation.</div>
       <div class="kpis">
         ${card('Articles vendus', fmt(mi.units))}
         ${card('CA généré', fmtEur(mi.ca))}
         ${card('Marge générée', fmtEur(mi.marge))}
       </div>`
    : `<div class="note" style="margin-top:8px">💡 L'impact (ventes & € sur tes réceptions) s'affichera après la prochaine génération.</div>`;
  return `<div class="note">Impact des recommandations pour <b>${STORE}</b> sur ce run.</div>
    <div class="kpis">
      ${card('Réceptions', inn.length, pc(inn)+' pièces à recevoir')}
      ${card('Expéditions', out.length, pc(out)+' pièces à envoyer')}
      ${card('Ruptures couvertes', rupt, 'réf. sous 7 j comblées')}
      ${card('Couverture après', covMoy+' j', '+'+gainMoy+' j en moyenne')}
    </div>${impact}
    <div id="store_valo"></div>`;
}
// Argent genere par les ENVOIS du magasin vers d'autres magasins (credit expediteur)
async function loadStoreValo(store){
  const box=document.getElementById('store_valo'); if(!box||!window.ValoStore) return;
  let rows=[]; try{ rows=await window.ValoStore.all(); }catch(e){ return; }
  const mine=(rows||[]).filter(r=>r.type==='interstore' && r.expediteur===store);
  if(!mine.length) return;
  const u=mine.reduce((s,r)=>s+(+r.cumul_units||0),0);
  const ca=mine.reduce((s,r)=>s+(+r.cumul_ca||0),0);
  const mg=mine.reduce((s,r)=>s+(+r.cumul_marge||0),0);
  const byDest={}; mine.forEach(r=>{ const d=byDest[r.destinataire]=byDest[r.destinataire]||{ca:0,units:0}; d.ca+=+r.cumul_ca||0; d.units+=+r.cumul_units||0; });
  const tops=Object.entries(byDest).sort((a,b)=>b[1].ca-a[1].ca).slice(0,4)
    .map(([k,v])=>`<span class="vchip">${k} · ${fmtEur(v.ca)}</span>`).join('');
  const card=(l,v,d)=>`<div class="kpi"><div class="label">${l}</div><div class="val">${v}</div>${d?`<div class="delta good">${d}</div>`:''}</div>`;
  box.innerHTML = `<h3 class="valo-h" style="margin-top:24px"><span class="ico">${icon('upload')}</span> L'argent que tes envois ont rapporté ailleurs</h3>
    <div class="kpis">
      ${card('CA généré', fmtEur(ca), u+' pièces vendues ailleurs')}
      ${card('Marge générée', fmtEur(mg))}
    </div>${tops?`<div class="vchips">${tops}</div>`:''}`;
}

function renderStore(){
  navStore();
  document.querySelector('.brand b').textContent = 'STOCKFLOW.AI';
  document.querySelector('.brand span').textContent = STORE;
  document.getElementById('tbBrand').textContent = STORE;
  const T=STORE_TABS.find(t=>t.id===stab);
  document.getElementById('ttl').textContent = T.label;
  document.getElementById('sub').textContent = 'Magasin '+STORE;
  const c=document.getElementById('content'); c.className='content';
  const switcher = STORES.length>1 ? `<div class="storeswitch"><label>Magasin</label>
    <select id="storeSel">${STORES.map(s=>`<option ${s===STORE?'selected':''}>${s}</option>`).join('')}</select></div>` : '';
  c.innerHTML = switcher + {expedier:renderExpedier, recevoir:renderRecevoir, reassort:renderReassort, grilles:renderGrilles, stats:renderStoreStats, urgent:renderUrgent}[stab]();
  const ss=document.getElementById('storeSel'); if(ss) ss.onchange=e=>{ STORE=e.target.value; openDest=null; renderStore(); };
  if(stab==='expedier') bindExpedier(c);
  if(stab==='reassort') loadReassort(c, STORE);
  if(stab==='stats') loadStoreValo(STORE);
  if(stab==='urgent') bindUrgent(c);
  if(PREVIEW){ const ba=document.getElementById('backAdmin'); if(ba) ba.onclick=()=>{PREVIEW=false;MODE='admin';render();}; }
}

// ============================================================
//  DEMANDES URGENTES (cote admin)
// ============================================================
function renderDemandes(){
  return `<div class="note">Demandes urgentes des magasins. Valide ou refuse — le magasin voit la décision.</div>
    <div id="d_list" class="cardcol"><div class="empty">Chargement…</div></div>`;
}
function demandeCard(r){
  const pend=r.statut==='en_attente';
  return `<div class="tcard" data-req="${r.id}"><div class="top">${statutPill(r.statut)}
      <span class="score" style="font-size:15px">${r.magasin||''}</span></div>
    <div class="flux">${r.reference}${r.taille?` <span style="color:var(--muted);font-weight:600">· ${r.taille}</span>`:''}</div>
    <div class="meta"><span><span class="k">Qté</span>${r.quantite||1}</span><span><span class="k">Le</span>${(r.created_at||'').slice(0,10)}</span></div>
    ${r.motif?`<div class="motif">${r.motif}</div>`:''}
    ${pend?`<div class="donorsug" data-ref="${(r.reference||'').replace(/"/g,'&quot;')}" data-taille="${(r.taille||'').replace(/"/g,'&quot;')}" data-mag="${r.magasin||''}"></div>`:''}
    ${pend?`<div class="dact"><button class="val" data-dec="validee">✓ Valider</button><button class="ref" data-dec="refusee">✕ Refuser</button></div>`:''}
  </div>`;
}
// Proposition de magasin(s) depanneur(s) : surplus mobilisable sur la reference.
function donorSugHTML(items, reqTaille){
  if(!items || !items.length) return '';
  const covTxt=c=>(c==null||c==='')?'':(c>=999?'stock dormant':(Math.round(c)+' j'));
  const line=d=>`<div class="dsug-row"><span class="dsug-mag">🏬 ${d.magasin}</span>`
    +`<span class="dsug-t">${d.taille}</span>`
    +`<span class="dsug-q">${d.qte_don} dispo</span>`
    +(covTxt(d.couverture_j)?`<span class="dsug-c">couv. ${covTxt(d.couverture_j)}</span>`:'')+`</div>`;
  const exact=reqTaille? items.filter(d=>String(d.taille).toUpperCase()===String(reqTaille).toUpperCase()):[];
  const autres=items.filter(d=>exact.indexOf(d)<0);
  const head=exact.length?`Peut dépanner (taille ${reqTaille})`:(reqTaille?`Aucun surplus en ${reqTaille} — autres tailles dispo`:'Peut dépanner');
  const shown=(exact.length?exact:autres).slice(0,3);
  return `<div class="dsug"><div class="dsug-h">💡 ${head}</div>${shown.map(line).join('')}</div>`;
}
async function fillDonorSug(el){
  if(!window.DonorStore) return;
  const ref=el.dataset.ref, taille=el.dataset.taille, mag=el.dataset.mag;
  if(!ref) return;
  let items=[]; try{ items=await window.DonorStore.forRef(ref, taille); }catch(e){ return; }
  items=(items||[]).filter(d=>d.magasin!==mag && (+d.qte_don||0)>0)
    .sort((a,b)=>(+b.couverture_j||0)-(+a.couverture_j||0));
  const html=donorSugHTML(items, taille);
  if(html) el.innerHTML=html;
}
async function loadDemandes(){
  const box=document.getElementById('d_list'); if(!box) return;
  let reqs=[]; try{ reqs=await window.UrgentStore.listAll(); }catch(e){ box.innerHTML=`<div class="empty">Erreur : ${e.message||e}</div>`; return; }
  const pend=reqs.filter(r=>r.statut==='en_attente').length;
  box.innerHTML = (pend?`<div class="note"><b>${pend}</b> demande(s) en attente</div>`:'')
    + (reqs.length? reqs.map(demandeCard).join('') : `<div class="empty">Aucune demande.</div>`);
  box.querySelectorAll('[data-req]').forEach(el=>el.querySelectorAll('button[data-dec]').forEach(btn=>
    btn.onclick=async()=>{ btn.disabled=true; try{ await window.UrgentStore.decide(el.dataset.req, btn.dataset.dec);}catch(e){} loadDemandes(); }));
  box.querySelectorAll('.donorsug').forEach(fillDonorSug);
}
// Hook par defaut (prototype/demo) : pas de proposition hors site heberge.
window.DonorStore = window.DonorStore || { async forRef(){ return []; } };

// ============================================================
//  DIFFERENCES signalees par les magasins (cote admin)
// ============================================================
function renderDifferences(){
  return `<div class="note">Différences signalées par les magasins pendant la préparation des expéditions.</div>
    <div id="diff_list" class="cardcol"><div class="empty">Chargement…</div></div>`;
}
function diffCard(x){
  return `<div class="tcard"><div class="top">
      <span class="pill" style="background:var(--amber-bg);color:var(--amber)">⚠ Différence</span>
      <span class="score" style="font-size:15px">${x.expediteur} → ${x.destinataire}</span></div>
    <div class="flux">${x.reference} <span style="color:var(--muted);font-weight:600">· ${x.taille}</span></div>
    <div class="meta"><span><span class="k">Qté prévue</span>${x.quantite}</span>${x.marque?`<span><span class="k">Marque</span>${x.marque}</span>`:''}${x.updated_at?`<span><span class="k">Signalée</span>${String(x.updated_at).slice(0,10)}</span>`:''}</div>
  </div>`;
}
async function loadDifferences(){
  const box=document.getElementById('diff_list'); if(!box) return;
  let items=[]; try{ items=await window.DiffStore.list(); }catch(e){ box.innerHTML=`<div class="empty">Erreur : ${e.message||e}</div>`; return; }
  box.innerHTML = (items.length?`<div class="note"><b>${items.length}</b> différence(s) signalée(s)</div>`:'')
    + (items.length? items.map(diffCard).join('') : `<div class="empty">Aucune différence signalée. 👍</div>`);
}

// ============================================================
//  REASSORT CENTRAL (CENTRAL -> magasins) — sortie A + import Fastmag (B)
// ============================================================
function renderReassort(){
  return `<div class="note">Réassort central de la semaine : <b>CENTRAL → magasins</b>. Sa sortie alimente aussi le picking des transferts inter-magasins (le besoin résiduel en tient compte).</div>
    <div id="rc_head"></div>
    <div id="rc_list" class="cardcol"><div class="empty">Chargement…</div></div>`;
}
function reassortCard(x){
  const p=(x.priorite||''); const isP1=p.indexOf('P1')===0; const isP2=p.indexOf('P2')===0;
  const col=isP1?'var(--red)':(isP2?'var(--amber)':'var(--muted)');
  const bg=isP1?'var(--red-bg)':(isP2?'var(--amber-bg)':'var(--chip)');
  return `<div class="tcard"><div class="top">
      <span class="pill" style="background:${bg};color:${col}">${p||'—'}</span>
      <span class="score" style="font-size:15px">${x.boutique}</span></div>
    <div class="flux">${x.reference} <span style="color:var(--muted);font-weight:600">· ${x.taille}</span></div>
    <div class="meta"><span><span class="k">Qté</span>${x.qte}</span>${x.marque?`<span><span class="k">Marque</span>${x.marque}</span>`:''}${(x.couverture_j!=null&&x.couverture_j!=='')?`<span><span class="k">Couv.</span>${x.couverture_j} j</span>`:''}${x.tailles_apres?`<span><span class="k">Après</span>${x.tailles_apres}</span>`:''}</div>
    ${x.commentaire?`<div class="motif">${x.commentaire}</div>`:''}
  </div>`;
}
async function loadReassort(root, store){
  const box=(root||document).querySelector('#rc_list'); if(!box) return;
  const head=(root||document).querySelector('#rc_head');
  if(!window.ReassortStore){ box.innerHTML=`<div class="empty">Disponible sur le site hébergé.</div>`; return; }
  let items=[]; try{ items=await window.ReassortStore.list(store); }
  catch(e){ box.innerHTML=`<div class="empty">Erreur : ${e.message||e}</div>`; return; }
  if(!items.length){ if(head) head.innerHTML='';
    box.innerHTML=`<div class="empty">Aucun réassort central pour ce run.${store?'':" Importe un fichier « Stock CENTRAL » dans l'onglet Générer."}</div>`; return; }
  const pieces=items.reduce((s,x)=>s+(+x.qte||0),0);
  const nbBout=new Set(items.map(x=>x.boutique)).size;
  if(head){
    let dl='';
    if(!store && window.ReassortStore.fastmagUrl){
      try{ const u=await window.ReassortStore.fastmagUrl(); if(u) dl+=`<a class="btn ico-btn" href="${u}" style="text-decoration:none">${icon('download')}Import Fastmag</a>`; }catch(e){}
    }
    if(!store && window.ReassortStore.excelUrl){
      try{ const u=await window.ReassortStore.excelUrl(); if(u) dl+=`<a class="btn ghost ico-btn" href="${u}" style="text-decoration:none">${icon('chart')}Classeur Excel</a>`; }catch(e){}
    }
    head.innerHTML=`<div class="note"><b>${items.length}</b> ligne(s) · <b>${pieces}</b> pièces${store?'':` · ${nbBout} magasin(s)`}</div>`
      +(dl?`<div style="display:flex;gap:10px;flex-wrap:wrap;margin:2px 0 14px">${dl}</div>`:'');
  }
  box.innerHTML=items.map(reassortCard).join('');
}
// Hook par defaut (prototype/demo) : pas de reassort central hors site heberge.
window.ReassortStore = window.ReassortStore || { async list(){ return []; } };

// ============================================================
//  VALORISATION — argent genere par les pieces deplacees (2 pistes)
// ============================================================
function valoSummary(rows){
  const z=()=>({units:0,ca:0,marge:0});
  const s={central:{...z(),par_dest:{}}, interstore:{...z(),par_exp:{},par_dest:{}}};
  const add=(m,k,r)=>{ if(!k) return; (m[k]=m[k]||z()); m[k].units+=+r.cumul_units||0; m[k].ca+=+r.cumul_ca||0; m[k].marge+=+r.cumul_marge||0; };
  (rows||[]).forEach(r=>{ const t=r.type; if(!s[t]) return;
    s[t].units+=+r.cumul_units||0; s[t].ca+=+r.cumul_ca||0; s[t].marge+=+r.cumul_marge||0;
    add(s[t].par_dest, r.destinataire, r); if(t==='interstore') add(s[t].par_exp, r.expediteur, r); });
  return s;
}
function valoRows(map, key){
  return Object.entries(map||{}).map(([k,v])=>({k, ...v})).sort((a,b)=>b[key]-a[key]);
}
function valoList(map){
  const rows=valoRows(map,'marge').filter(r=>r.ca>0||r.units>0).slice(0,14);
  if(!rows.length) return `<div class="empty">Rien pour le moment.</div>`;
  return `<div class="cardcol">`+rows.map(r=>`<div class="vrow">
      <span class="vmag">${r.k}</span>
      <span class="vmeta">${r.units} pcs</span>
      <span class="vca">${fmtEur(r.ca)}</span>
      <span class="vmarge">marge ${fmtEur(r.marge)}</span></div>`).join('')+`</div>`;
}
function renderValo(){
  return `<div class="note">Argent généré par les pièces déplacées — cumulé dans le temps, plafonné au nombre envoyé. Apparaît une fois que les ventes arrivent (≈ 2ᵉ génération).</div>
    <div id="valo_body"><div class="empty">Chargement…</div></div>`;
}
function valoHero(tot){
  if(!tot) return '';
  const c=tot.central||{ca:0,marge:0}, i=tot.interstore||{ca:0,marge:0};
  const ca=(+c.ca||0)+(+i.ca||0), mg=(+c.marge||0)+(+i.marge||0);
  if(ca<=0 && mg<=0) return '';
  return `<div class="valo-hero">
      <div class="vh-label">Généré depuis le début</div>
      <div class="vh-val">${fmtEur(ca)}</div>
      <div class="vh-sub">dont marge <b>${fmtEur(mg)}</b> · central ${fmtEur(c.ca)} · inter-magasins ${fmtEur(i.ca)}</div>
    </div>`;
}
async function loadValo(){
  const box=document.getElementById('valo_body'); if(!box) return;
  if(!window.ValoStore){ box.innerHTML=`<div class="empty">Disponible sur le site hébergé.</div>`; return; }
  let rows=[], tot=null;
  try{ rows=await window.ValoStore.all(); }catch(e){ box.innerHTML=`<div class="empty">Erreur : ${e.message||e}</div>`; return; }
  try{ tot=window.ValoStore.total?await window.ValoStore.total():null; }catch(e){}
  const hero=valoHero(tot);
  if(!rows.length && !hero){ box.innerHTML=`<div class="empty">Pas encore de valorisation — elle se remplit dès que les ventes des réassorts arrivent.</div>`; return; }
  const s=valoSummary(rows);
  const kpi=(l,v,d)=>`<div class="kpi"><div class="label">${l}</div><div class="val">${v}</div>${d?`<div class="delta good">${d}</div>`:''}</div>`;
  box.innerHTML = hero + `
    <h3 class="valo-h${hero?' vh-first':''}"><span class="ico">${icon('warehouse')}</span> Réassort central → magasins</h3>
    <div class="kpis">
      ${kpi('CA généré', fmtEur(s.central.ca), s.central.units+' pièces vendues')}
      ${kpi('Marge générée', fmtEur(s.central.marge))}
    </div>
    <h3 class="valo-h"><span class="ico">${icon('shuffle')}</span> Transferts inter-magasins</h3>
    <div class="kpis">
      ${kpi('CA généré', fmtEur(s.interstore.ca), s.interstore.units+' pièces vendues')}
      ${kpi('Marge générée', fmtEur(s.interstore.marge))}
    </div>
    <h3 class="valo-h"><span class="ico">${icon('upload')}</span> Généré par magasin expéditeur (leurs envois inter-magasins)</h3>
    ${valoList(s.interstore.par_exp)}`;
}
// Hook par defaut (prototype/demo).
window.ValoStore = window.ValoStore || { async all(){ return []; }, async total(){ return null; } };

// ============================================================
//  UTILISATEURS (back-office admin)
// ============================================================
function renderUsers(){
  const opts=boutiques().map(b=>`<label class="ucheck"><input type="checkbox" value="${b}"> ${b}</label>`).join('');
  return `<div class="note">Crée les comptes de l'équipe et affecte un ou plusieurs magasins. Aucun magasin coché = compte administrateur (accès complet).</div>
    <div class="panel" style="padding:16px;max-width:640px;margin-bottom:20px">
      <div class="ufield"><label>E-mail</label><input id="nu_email" type="email" placeholder="toulouse@fk.local"></div>
      <div class="ufield"><label>Mot de passe (min. 6 caractères)</label><input id="nu_pwd" type="text" placeholder="mot de passe"></div>
      <div class="ufield"><label>Magasins</label><div class="uchecks" id="nu_stores">${opts||'<span style="color:var(--muted);font-size:13px">Aucun magasin dans ce run.</span>'}</div></div>
      <button class="btn" id="nu_add">➕ Créer le compte</button>
      <div id="nu_err" style="color:var(--red);font-size:12.5px;margin-top:10px;min-height:14px"></div>
    </div>
    <h3 style="font-family:var(--font-display);text-transform:uppercase;letter-spacing:.05em;font-size:13px;margin:6px 2px 12px">Comptes existants</h3>
    <div id="u_list" class="cardcol"><div class="empty">Chargement…</div></div>`;
}
function userCard(u){
  const isAdmin=!(u.stores&&u.stores.length);
  const opts=boutiques().map(b=>`<label class="ucheck"><input type="checkbox" value="${b}" ${u.stores&&u.stores.indexOf(b)>=0?'checked':''}> ${b}</label>`).join('');
  return `<div class="tcard" data-uid="${u.id}">
    <div class="top"><span class="pill" style="${isAdmin?'background:var(--blue-bg);color:var(--blue)':'background:var(--green-bg);color:var(--green)'}">${isAdmin?'ADMIN':'MAGASIN'}</span>
      <span class="score" style="font-size:12.5px">${(u.created_at||'').slice(0,10)}</span></div>
    <div class="flux" style="font-size:15px;text-transform:none;letter-spacing:0">${u.email||''}</div>
    <div class="meta"><span><span class="k">Accès</span>${isAdmin?'Tout (administrateur)':u.stores.join(' · ')}</span></div>
    <div class="ueditor" hidden style="margin-top:8px">
      <div class="uchecks">${opts}</div>
      <div class="dact"><button class="val usave">Enregistrer</button><button class="ucancel">Annuler</button></div>
    </div>
    <div class="dact uactions">
      <button class="uedit">Modifier les magasins</button>
      <button class="ref udel">Supprimer</button>
    </div>
  </div>`;
}
async function loadUsers(){
  const box=document.getElementById('u_list'); if(!box) return;
  if(!window.UserAdmin){ box.innerHTML=`<div class="empty">Disponible sur le site hébergé (backend requis).</div>`; return; }
  let list=[]; try{ const r=await window.UserAdmin.list(); list=r.users||[]; }
  catch(e){ box.innerHTML=`<div class="empty">Erreur : ${e.message||e}</div>`; return; }
  box.innerHTML = list.length? list.map(userCard).join('') : `<div class="empty">Aucun compte pour le moment.</div>`;
  box.querySelectorAll('[data-uid]').forEach(card=>{
    const uid=card.dataset.uid;
    const ed=card.querySelector('.ueditor'), act=card.querySelector('.uactions');
    card.querySelector('.uedit').onclick=()=>{ ed.hidden=false; act.hidden=true; };
    card.querySelector('.ucancel').onclick=()=>{ ed.hidden=true; act.hidden=false; };
    card.querySelector('.usave').onclick=async(e)=>{ e.target.disabled=true;
      const stores=[...ed.querySelectorAll('input:checked')].map(i=>i.value);
      try{ await window.UserAdmin.setStores(uid, stores); loadUsers(); }
      catch(err){ e.target.disabled=false; alert('Erreur : '+(err.message||err)); } };
    card.querySelector('.udel').onclick=async(e)=>{ if(!confirm('Supprimer ce compte ?')) return; e.target.disabled=true;
      try{ await window.UserAdmin.remove(uid); loadUsers(); }
      catch(err){ e.target.disabled=false; alert('Erreur : '+(err.message||err)); } };
  });
}
function bindUsers(root){
  loadUsers();
  const add=root.querySelector('#nu_add'); if(!add) return;
  add.onclick=async()=>{
    const err=root.querySelector('#nu_err'); err.textContent='';
    const email=root.querySelector('#nu_email').value.trim();
    const pwd=root.querySelector('#nu_pwd').value;
    const stores=[...root.querySelectorAll('#nu_stores input:checked')].map(i=>i.value);
    if(!email||pwd.length<6){ err.textContent="E-mail requis et mot de passe d'au moins 6 caractères."; return; }
    if(!window.UserAdmin){ err.textContent='Disponible sur le site hébergé.'; return; }
    add.disabled=true;
    try{ await window.UserAdmin.create(email,pwd,stores);
      root.querySelector('#nu_email').value=''; root.querySelector('#nu_pwd').value='';
      root.querySelectorAll('#nu_stores input:checked').forEach(i=>i.checked=false);
      loadUsers();
    }catch(e){ err.textContent='Erreur : '+(e.message||e); }
    add.disabled=false;
  };
}

// ============================================================
//  GENERER une mise a jour (upload fichiers -> moteur -> Supabase)
// ============================================================
function renderGenerer(){
  return `<div class="note">Mets à jour les transferts en important les nouveaux fichiers Fastmag. Le calcul se lance puis remplace l'analyse affichée.</div>
    <div class="panel" style="padding:18px;max-width:560px">
      <div class="ufield"><label>Stock — obligatoire</label><input type="file" id="g_stock" accept=".csv,.xlsx"></div>
      <div class="ufield"><label>Ventes — obligatoire</label><input type="file" id="g_ventes" accept=".csv,.xlsx"></div>
      <div class="ufield"><label>Stock CENTRAL — optionnel (réassort central)</label><input type="file" id="g_central" accept=".xls,.xlsx,.csv,.txt"><div style="font-size:11.5px;color:var(--muted);margin-top:4px">Active le réassort central : CENTRAL → magasins d'abord, puis son résultat alimente le picking des transferts inter-magasins (A + B).</div></div>
      <div class="ufield"><label>Réassort Picking — optionnel</label><input type="file" id="g_reassort" accept=".xlsx,.csv"></div>
      <div class="ufield"><label>Objectifs — optionnel</label><input type="file" id="g_objectif" accept=".csv,.xlsx"></div>
      <div class="ufield"><label>Cible de couverture receveur (jours)</label><input type="number" id="g_cible" value="21" min="1" style="max-width:120px"></div>
      <button class="btn" id="g_run" style="margin-top:6px">⚙️ Générer les transferts</button>
      <div id="g_status" style="margin-top:14px;font-size:13px;color:var(--muted);min-height:18px"></div>
    </div>`;
}
// Overlay de generation : logo + 3 mots comme etapes (analyse -> optimise -> gagne)
function genHint(msg){ const h=document.getElementById('genovHint'); if(h) h.textContent=msg||''; }
window.__onGenProgress = genHint;
window.__genStep = function(name){
  const ov=document.getElementById('genov'); if(!ov) return;
  const order=['analyse','optimise','gagne']; const idx=order.indexOf(name);
  ov.querySelectorAll('.gstep').forEach((el,i)=>{
    el.classList.toggle('active', i===idx);
    el.classList.toggle('done', i<idx);
  });
};
function showGenOverlay(){ const ov=document.getElementById('genov'); if(!ov) return;
  ov.hidden=false; requestAnimationFrame(()=>ov.classList.add('on')); window.__genStep('analyse'); genHint('Envoi des fichiers…'); }
function hideGenOverlay(){ const ov=document.getElementById('genov'); if(!ov) return;
  ov.classList.remove('on'); setTimeout(()=>{ ov.hidden=true; }, 400); }

function bindGenerer(root){
  const st=root.querySelector('#g_status');
  root.querySelector('#g_run').onclick=async()=>{
    const stock=root.querySelector('#g_stock').files[0];
    const ventes=root.querySelector('#g_ventes').files[0];
    if(!stock||!ventes){ st.style.color='var(--red)'; st.textContent='Ajoute au moins le fichier Stock et le fichier Ventes.'; return; }
    if(!window.doGenerate){ st.style.color='var(--amber)'; st.textContent="La génération est disponible sur le site hébergé (backend requis)."; return; }
    const cible=parseInt(root.querySelector('#g_cible').value)||21;
    root.querySelector('#g_run').disabled=true; st.textContent='';
    showGenOverlay();
    try{
      const res=await window.doGenerate({stock, ventes,
        reassort:root.querySelector('#g_reassort').files[0],
        objectif:root.querySelector('#g_objectif').files[0],
        central:root.querySelector('#g_central').files[0], cible});
      window.__genStep('gagne');
      genHint(`✅ ${res.nb_transferts} transferts générés${res.perimetre?' · '+res.perimetre:''}`);
      setTimeout(()=>location.reload(), 1800);
    }catch(e){
      hideGenOverlay();
      st.style.color='var(--red)'; st.textContent='Erreur : '+(e.message||e);
      root.querySelector('#g_run').disabled=false;
    }
  };
}

// Hooks par defaut (prototype/demo) : role via #store=XXX, demandes en localStorage.
// La version Supabase remplace roleInfo + UrgentStore.
window.roleInfo = window.roleInfo || (async ()=>{
  const m=(location.hash||'').match(/store=([^&]+)/);
  if(m){ const stores=decodeURIComponent(m[1]).split(',').map(s=>s.trim()).filter(Boolean);
    return {mode:'store', stores}; }
  return {mode:'admin', stores:[]};
});
window.UrgentStore = window.UrgentStore || {
  _k:'sf_urgent',
  _all(){ try{return JSON.parse(localStorage.getItem(this._k)||'[]')}catch(e){return []} },
  _save(a){ localStorage.setItem(this._k, JSON.stringify(a)); },
  async create(o){ const a=this._all(); a.unshift({...o, id:'loc'+a.length+'_'+(o.reference||''), statut:'en_attente',
      created_at:new Date().toISOString()}); this._save(a); },
  async listMine(store){ return this._all().filter(r=>r.magasin===store); },
  async listAll(){ return this._all(); },
  async decide(id,dec){ const a=this._all(); const r=a.find(x=>x.id===id); if(r) r.statut=dec; this._save(a); }
};
// Expeditions validees (demo/prototype) : localStorage par run
window.ShipStore = window.ShipStore || {
  _k(){ return 'sf_ship_'+((DATA&&DATA.meta&&DATA.meta.runid)||'run'); },
  async load(){ try{ return JSON.parse(localStorage.getItem(this._k())||'{}'); }catch(e){ return {}; } },
  async validate(exp,dest){ const m=await this.load(); m[exp+'>'+dest]=true; localStorage.setItem(this._k(), JSON.stringify(m)); },
  async unvalidate(exp,dest){ const m=await this.load(); delete m[exp+'>'+dest]; localStorage.setItem(this._k(), JSON.stringify(m)); }
};
// Differences (demo/prototype) : lues depuis l'etat local des revues (=='diff')
window.DiffStore = window.DiffStore || {
  async list(){
    const out=[];
    DATA.transfers.forEach(r=>{ if(reviews[r[C.n]]==='diff') out.push({
      reference:r[C.ref], taille:r[C.taille], quantite:r[C.qte],
      expediteur:r[C.exp], destinataire:r[C.dest], marque:r[C.marque], updated_at:'' }); });
    return out;
  }
};

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
  try{ shipments = window.ShipStore ? await window.ShipStore.load() : {}; }catch(e){ shipments={}; }
  try{ RUNS_CACHE = window.listRuns ? await window.listRuns() : null; }catch(e){ RUNS_CACHE=null; }
  const role = await (window.roleInfo ? window.roleInfo() : {mode:'admin', stores:[]});
  MODE = role.mode;
  STORES = role.stores || (role.store ? [role.store] : []);
  STORE = STORES[0] || null;
  if(MODE==='store' && STORE){ PREVIEW=false; renderStore(); } else { MODE='admin'; render(); }
  // bouton de deconnexion : visible seulement si un mecanisme est fourni (Supabase)
  if(window.doLogout){ const lo=document.getElementById('logout');
    if(lo){ lo.style.display=''; lo.onclick=window.doLogout; } }
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
