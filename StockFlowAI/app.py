"""StockFlow AI - mini-site local (glisser-deposer).

Lancement :
    pip install -r requirements.txt
    streamlit run app.py

Ouvre une page dans le navigateur : deposez vos fichiers (STOCK, VENTES, et si
disponible REASSORT / OBJECTIF), reglez la cible de couverture, cliquez sur
« Lancer l'analyse », consultez les indicateurs et telechargez l'Excel complet.

Le moteur est identique a la ligne de commande : cette page n'est que l'habillage.
"""

from __future__ import annotations

import io
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

from stockflow import MOTEUR_VERSION
from stockflow.app_service import build_params, run_analysis


st.set_page_config(page_title="StockFlow AI", page_icon="📦", layout="wide")

# --- En-tete --------------------------------------------------------------
st.title("📦 StockFlow AI — recommandations de transferts")
st.caption(f"Moteur v{MOTEUR_VERSION} · aide a la decision · **aucun transfert n'est execute automatiquement**")

# --- Reglages (barre laterale) --------------------------------------------
with st.sidebar:
    st.header("Reglages")
    today = st.date_input("Date d'analyse", value=pd.Timestamp("2026-07-13"))
    st.subheader("Couvertures (jours)")
    cible = st.number_input("Cible magasin", 5, 90, 14, help="Couverture visee apres reassort")
    min_exp = st.number_input("Minimum expediteur", 0, 60, 10,
                              help="A conserver chez le donneur ; doit rester sous la cible")
    min_web = st.number_input("Minimum Web", 0, 90, 14, help="Reserve Web protegee")
    st.subheader("Regles")
    nb_dest = st.number_input("Destinations max / expediteur", 1, 10, 4)
    seuil = st.slider("Score minimum retenu", 0, 100, 60)
    if min_exp >= cible:
        st.warning("Le minimum expediteur devrait rester **sous** la cible, "
                   "sinon les donneurs ne peuvent quasiment pas ceder de stock.")

# --- Depot des fichiers ----------------------------------------------------
st.subheader("1 · Deposez vos fichiers")
c1, c2 = st.columns(2)
with c1:
    f_stock = st.file_uploader("Stock (CSV) — obligatoire", type=["csv"], key="stock")
    f_ventes = st.file_uploader("Ventes detaillees (CSV) — obligatoire", type=["csv"], key="ventes")
with c2:
    f_reassort = st.file_uploader("Reassorts programmes (XLSX) — optionnel", type=["xlsx"], key="reassort")
    f_objectif = st.file_uploader("Objectifs (CSV) — optionnel", type=["csv"], key="objectif")

st.info("Astuce : sans fichier « Reassorts », le moteur ne connait pas le stock "
        "en transit ; sans « Magasins » (a venir), la proximite geo et le bonus "
        "flagship sont neutres. Les regles se reactivent des que les fichiers arrivent.")

run = st.button("🚀 Lancer l'analyse", type="primary", disabled=not (f_stock and f_ventes))


def _buf(uploaded):
    """Copie l'upload dans un buffer memoire re-lisible."""
    if uploaded is None:
        return None
    return io.BytesIO(uploaded.getvalue())


# --- Execution -------------------------------------------------------------
if run:
    with st.spinner("Analyse en cours (peut prendre 1 a 2 min sur un gros reseau)…"):
        export_path = Path(tempfile.gettempdir()) / f"stockflow_{pd.Timestamp(today).date()}.xlsx"
        params = build_params(cible=cible, min_expediteur=min_exp, min_web=min_web,
                              nb_max_destinations=nb_dest, seuil_score=seuil)
        result, datasets = run_analysis(
            stock=_buf(f_stock), ventes=_buf(f_ventes),
            reassort=_buf(f_reassort), objectif=_buf(f_objectif),
            params=params, today=pd.Timestamp(today), export_path=export_path,
        )

    if result.blocked:
        st.error("⛔ Traitement bloque : " + result.message)
        st.dataframe(result.quality_report.anomalies_df(), use_container_width=True)
        st.stop()

    st.success(f"✅ {len(result.transfers)} transferts recommandes "
               f"({result.journal.get('nb_iterations')} iterations, "
               f"mode {result.journal.get('mode_optimisation','?')}).")

    # --- KPI avant/apres ---
    sim = result.simulation_global.set_index("indicateur")

    def _kpi(label, key, inverse=False):
        av = float(sim.loc[key, "avant"]); ap = float(sim.loc[key, "apres"])
        delta = ap - av
        st.metric(label, f"{ap:,.0f}", f"{delta:+,.0f}",
                  delta_color="inverse" if inverse else "normal")

    st.subheader("2 · Impact reseau (avant → apres)")
    k1, k2, k3, k4 = st.columns(4)
    with k1: _kpi("Ruptures", "ruptures", inverse=True)
    with k2: _kpi("Refs sous 7 jours", "refs_sous_7j", inverse=True)
    with k3: _kpi("Couverture moyenne (j)", "couverture_moyenne")
    with k4: _kpi("Score sante reseau", "score_sante_reseau")
    with st.expander("Voir tous les indicateurs"):
        st.dataframe(result.simulation_global, use_container_width=True, hide_index=True)

    # --- Telechargement Excel ---
    st.subheader("3 · Recommandations")
    with open(export_path, "rb") as fh:
        st.download_button("⬇️ Telecharger l'Excel complet (7 onglets)",
                           data=fh.read(),
                           file_name=export_path.name,
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           type="primary")

    # --- Apercu filtrable des transferts ---
    t = result.transfers.copy()
    if not t.empty:
        boutiques = sorted(set(t["expediteur"]) | set(t["destinataire"]))
        sel = st.selectbox("Filtrer sur une boutique (expediteur ou destinataire)",
                           ["— toutes —"] + boutiques)
        view = t
        if sel != "— toutes —":
            view = t[(t["expediteur"] == sel) | (t["destinataire"] == sel)]
        cols = ["priorite", "score", "expediteur", "destinataire", "reference",
                "couleur", "taille", "quantite", "cov_dest_avant", "cov_dest_apres",
                "grille_avant", "grille_apres", "picking_prevu", "motif"]
        st.dataframe(view[[c for c in cols if c in view.columns]]
                     .sort_values("score", ascending=False),
                     use_container_width=True, hide_index=True, height=420)
        st.caption(f"{len(view)} transferts affiches. "
                   "Le detail complet (stocks/couvertures avant-apres, distances…) "
                   "est dans l'onglet 1 de l'Excel.")

    # --- Cas non traites ---
    if result.cas_non_traites is not None and not result.cas_non_traites.empty:
        with st.expander(f"Cas non traites ({len(result.cas_non_traites)})"):
            st.dataframe(result.cas_non_traites.head(500), use_container_width=True, hide_index=True)
else:
    st.stop()
