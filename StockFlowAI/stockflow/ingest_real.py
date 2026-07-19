"""Adaptateur pour les exports reels (Fastmag : STOCK / VENTESTOCKFLOW / OBJECTIF).

Transforme les CSV reels en fichiers canoniques attendus par le moteur, sans
toucher au coeur. Choix structurants (a valider avec le metier) :

* ``reference``/``couleur`` sont derives de ``BarCode V2`` : modele = partie
  avant le dernier tiret, couleur = suffixe (ex. ``779229-04`` -> ref ``779229``
  couleur ``04``). 83% des barcodes suivent ce schema.
* ``taille`` est standardisee via :mod:`stockflow.sizes` ; ``categorie`` recoit
  la *famille de taille* (LETTRE / CHAUSSURE / ENFANT / AUTRE) qui pilote les
  tailles coeur.
* ``prix_vente`` (absent du stock) est recupere depuis le fichier de ventes.
* referentiel magasins minimal deduit des ``Code_Origine`` (ville = code,
  ``WEB`` detecte). Picking et historique absents => regles associees neutres.

Ces choix sont reversibles : fournir les fichiers Picking / Magasins / Historique
reactive les regles correspondantes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Tuple

import numpy as np
import pandas as pd

from .sizes import normalize_size


WEB_NAMES = {"WEB", "WEB_RETOUR", "ECOMMERCE", "ECOM"}


def _read_csv(path) -> pd.DataFrame:
    # utf-8-sig : neutralise le BOM present dans les exports (sinon il colle a
    # l'intitule de la premiere colonne). Accepte un chemin ou un fichier-memoire
    # (upload navigateur).
    return pd.read_csv(path, dtype=str, keep_default_na=False, na_values=[""],
                       encoding="utf-8-sig")


def _num(series: pd.Series) -> pd.Series:
    return pd.to_numeric(
        series.astype(str).str.replace(" ", "", regex=False)
        .str.replace(" ", "", regex=False).str.replace(",", ".", regex=False),
        errors="coerce",
    ).fillna(0.0)


def barcode_reference(bc: pd.Series) -> pd.Series:
    """Reference = code-barre COMPLET (un code-barre = un produit).

    On n'invente plus de reference/couleur en decoupant sur les tirets : les
    code-barres a plusieurs segments (ex. LL061074-BLANC-SHORT) etaient tronques
    a tort. Le code-barre entier est l'identifiant fiable, retrouvable tel quel
    dans le systeme source. La couleur/le type restent embarques dedans.
    """
    return bc.astype(str).str.strip()


def split_barcode(bc: pd.Series) -> Tuple[pd.Series, pd.Series]:
    """[obsolete] Ancien decoupage MODELE-COULEUR, conserve pour reference.

    Ne plus utiliser pour identifier un produit : voir barcode_reference.
    """
    s = bc.astype(str).str.strip()
    has_dash = s.str.contains("-", regex=False)
    ref = np.where(has_dash, s.str.rsplit("-", n=1).str[0], s)
    coul = np.where(has_dash, s.str.rsplit("-", n=1).str[-1], "UNI")
    return pd.Series(ref, index=bc.index).str.strip(), pd.Series(coul, index=bc.index).str.strip()


def _norm_sizes(series: pd.Series) -> Tuple[pd.Series, pd.Series]:
    """Normalise les tailles en travaillant sur les valeurs uniques (rapide)."""
    s = series.fillna("").astype("object").map(lambda x: str(x))
    uniques = s.unique()
    mapping = {u: normalize_size(u) for u in uniques}
    tn = s.map(lambda x: mapping[x][0])
    fam = s.map(lambda x: mapping[x][1])
    return tn, fam


def load_reassort(reassort_xlsx) -> pd.DataFrame:
    """Charge le fichier de reassorts programmes (sortie de l'agent existant).

    La feuille "Tous transferts" liste les reassorts CENTRAL -> boutique deja
    proposes. On les traite comme du stock EN TRANSIT vers la boutique
    destinataire (brief 2.4 / 5.1) : StockFlow n'a pas a les doubler, il calcule
    un besoin residuel net de ces reassorts.
    """
    try:
        tt = pd.read_excel(reassort_xlsx, sheet_name="Tous transferts")
    except Exception:
        return pd.DataFrame()
    if tt.empty or "Boutique" not in tt.columns:
        return pd.DataFrame()
    ref = barcode_reference(tt["Barcode"])
    taille, _ = _norm_sizes(tt["Taille"])
    qte = _num(tt.get("Qté proposée", tt.get("Qte proposee", 0)))
    pick = pd.DataFrame({
        "magasin": tt["Boutique"].astype(str).str.strip(),
        "reference": ref, "couleur": "", "taille": taille,
        "quantite_prevue": qte,
        "statut_reassort": "PROPOSE",          # non receptionne => en transit
        "id_mouvement": [f"RE{i:05d}" for i in range(len(tt))],
    })
    pick = pick[pick["quantite_prevue"] > 0]
    # agregation si doublons apres normalisation des tailles
    pick = pick.groupby(["magasin", "reference", "couleur", "taille"], as_index=False).agg(
        quantite_prevue=("quantite_prevue", "sum"),
        statut_reassort=("statut_reassort", "first"),
        id_mouvement=("id_mouvement", "first"))
    return pick


def _require_columns(df: pd.DataFrame, cols, label: str) -> None:
    """Verifie la presence des colonnes essentielles ; message clair si absentes."""
    missing = [c for c in cols if c not in df.columns]
    if missing:
        found = ", ".join(map(str, list(df.columns)[:30]))
        raise ValueError(
            f"Fichier {label} : colonne(s) manquante(s) : {', '.join(missing)}. "
            f"Colonnes trouvees : {found}")


def load_real_dataset(stock_csv, sales_csv, objectif_csv=None,
                      reassort_xlsx=None, ratio_prix_min: float = 0.25,
                      today: pd.Timestamp | None = None) -> Dict[str, pd.DataFrame]:
    today = pd.Timestamp(today) if today is not None else pd.Timestamp("2026-07-13")

    # ---------------- VENTES (grain jour x magasin x barcode x taille) --------
    vraw = _read_csv(sales_csv)
    _require_columns(vraw, ["BarCode V2", "Taille", "Code_Origine",
                            "Total QteVenteRetail", "Total MtVenteRetailTTC",
                            "Jours dans Date"], "VENTES")
    vref = barcode_reference(vraw["BarCode V2"])
    vtaille, vfam = _norm_sizes(vraw["Taille"])
    vqte = _num(vraw["Total QteVenteRetail"])
    vca = _num(vraw["Total MtVenteRetailTTC"])
    # prix de vente : optionnel. Absent -> derive du prix unitaire reel (CA / Qte).
    if "PrixVente" in vraw.columns:
        vprix = _num(vraw["PrixVente"])
    else:
        vprix = (vca / vqte.replace(0, np.nan)).fillna(0.0)
    v = pd.DataFrame({
        "magasin": vraw["Code_Origine"].str.strip(),
        "reference": vref, "couleur": "", "taille": vtaille, "famille": vfam,
        "marque": vraw.get("Marque Gp", pd.Series([""] * len(vraw))).astype(str).str.strip(),
        "saison": vraw.get("Saison", pd.Series([""] * len(vraw))).astype(str).str.strip(),
        "prix_vente": vprix,
        "qte": vqte,
        "ca": vca,
        "date": pd.to_datetime(vraw["Jours dans Date"], dayfirst=True, errors="coerce"),
    })
    # --- Garde-fou anti-erreur de saisie -----------------------------------
    # Une ligne de vente dont le prix unitaire REEL (CA / quantite) est tres
    # inferieur au prix de vente de base est suspecte : typiquement une quantite
    # saisie a tort (ex. 20 pieces au lieu d'1), ou un article "offert" a 0 €.
    # On neutralise sa quantite pour ne pas gonfler la demande (le transfert ne
    # doit pas etre declenche par une erreur de caisse). Seuil parametrable.
    pu_reel = v["ca"] / v["qte"].replace(0, np.nan)
    suspect = (v["qte"] > 1) & (v["prix_vente"] > 0) & (pu_reel < ratio_prix_min * v["prix_vente"])
    v_suspect = v[suspect].copy()
    if not v_suspect.empty:
        v.loc[suspect, ["qte", "ca"]] = 0.0

    anchor = v["date"].max()
    if pd.isna(anchor):
        anchor = today
    debut_7j = anchor - pd.Timedelta(days=6)
    v7 = v[v["date"] >= debut_7j]

    grp_keys = ["magasin", "reference", "couleur", "taille"]
    sales35 = v.groupby(grp_keys, as_index=False).agg(
        ventes_35j=("qte", "sum"), ca_35j=("ca", "sum"),
        date_derniere_vente=("date", "max"), famille=("famille", "first"),
        marque=("marque", "first"), saison=("saison", "first"),
    )
    sales7 = v7.groupby(grp_keys, as_index=False).agg(
        ventes_7j=("qte", "sum"), ca_7j=("ca", "sum"))
    sales = sales35.merge(sales7, on=grp_keys, how="left")
    sales[["ventes_7j", "ca_7j"]] = sales[["ventes_7j", "ca_7j"]].fillna(0.0)

    # prix de vente par (reference, couleur) puis par reference (fallback)
    prix_cc = (v[v["prix_vente"] > 0]
               .groupby(["reference", "couleur"])["prix_vente"].median())
    prix_ref = v[v["prix_vente"] > 0].groupby("reference")["prix_vente"].median()

    # ---------------- STOCK (grain magasin x barcode x taille) ----------------
    sraw = _read_csv(stock_csv)
    _require_columns(sraw, ["BarCode V2", "Taille", "Code_Origine", "Total Stock"], "STOCK")
    sref = barcode_reference(sraw["BarCode V2"])
    staille, sfam = _norm_sizes(sraw["Taille"])
    st = pd.DataFrame({
        "magasin": sraw["Code_Origine"].str.strip(),
        "reference": sref, "couleur": "", "taille": staille, "famille": sfam,
        "marque": sraw.get("Marque Gp", pd.Series([""] * len(sraw))).astype(str).str.strip(),
        "prix_achat": _num(sraw.get("PrixAchat", pd.Series([0.0] * len(sraw)))),
        "stock_physique": _num(sraw["Total Stock"]),
    })
    # agregation des doublons apres normalisation des tailles
    st = st.groupby(["magasin", "reference", "couleur", "taille"], as_index=False).agg(
        famille=("famille", "first"), marque=("marque", "first"),
        prix_achat=("prix_achat", "mean"), stock_physique=("stock_physique", "sum"))

    # prix de vente : (ref,coul) sinon ref sinon prix_achat/0.45
    st = st.merge(prix_cc.rename("pv_cc"), on=["reference", "couleur"], how="left")
    st = st.merge(prix_ref.rename("pv_ref"), on="reference", how="left")
    st["prix_vente"] = st["pv_cc"].fillna(st["pv_ref"]).fillna(st["prix_achat"] / 0.45)
    st.drop(columns=["pv_cc", "pv_ref"], inplace=True)

    up = st["magasin"].str.upper()
    st["indic_web"] = up.isin(WEB_NAMES)
    st["indic_picking"] = False
    st["ville"] = st["magasin"]                       # referentiel minimal
    st["categorie"] = st["famille"]                   # pilote les tailles coeur
    st["genre"] = ""
    st["statut_reference"] = "ACTIF"
    st["stock_disponible"] = st["stock_physique"]

    cols = [
        "magasin", "ville", "reference", "couleur", "taille", "stock_physique",
        "stock_disponible", "categorie", "genre", "marque", "prix_vente",
        "prix_achat", "statut_reference", "indic_web", "indic_picking",
    ]
    stocks = st[cols].copy()

    # --- Recuperation des ruptures ------------------------------------------
    # Le fichier stock ne liste que du stock positif : les tailles VENDUES mais
    # en rupture (stock 0) n'y figurent pas. On les materialise a 0 pour que le
    # moteur les voie comme ruptures a reassortir (sinon elles sont invisibles).
    keys = ["magasin", "reference", "couleur", "taille"]
    miss = sales.merge(st[keys].drop_duplicates(), on=keys, how="left", indicator=True)
    miss = miss[miss["_merge"] == "left_only"].drop(columns="_merge").copy()
    # Perimetre : on ne recupere les ruptures que pour les magasins presents dans
    # le fichier stock (les ventes de magasins hors perimetre, ex. PRESTA, sont
    # ignorees pour ne pas creer de faux receveurs).
    perimetre = set(st["magasin"].unique())
    miss = miss[miss["magasin"].isin(perimetre)]
    if not miss.empty:
        miss = miss.merge(prix_cc.rename("pv_cc"), on=["reference", "couleur"], how="left")
        miss = miss.merge(prix_ref.rename("pv_ref"), on="reference", how="left")
        up_m = miss["magasin"].str.upper()
        ruptures = pd.DataFrame({
            "magasin": miss["magasin"], "ville": miss["magasin"],
            "reference": miss["reference"], "couleur": miss["couleur"],
            "taille": miss["taille"], "stock_physique": 0.0, "stock_disponible": 0.0,
            "categorie": miss["famille"], "genre": "", "marque": miss["marque"],
            "prix_vente": miss["pv_cc"].fillna(miss["pv_ref"]).fillna(0.0),
            "prix_achat": 0.0, "statut_reference": "ACTIF",
            "indic_web": up_m.isin(WEB_NAMES), "indic_picking": False,
        })[cols]
        stocks = pd.concat([stocks, ruptures], ignore_index=True)

    sales_out = sales[[
        "magasin", "reference", "couleur", "taille",
        "ventes_35j", "ventes_7j", "ca_35j", "ca_7j", "date_derniere_vente",
    ]].copy()

    # ---------------- MAGASINS (referentiel minimal deduit) -------------------
    codes = pd.Index(sorted(set(stocks["magasin"]) | set(sales_out["magasin"])))
    stores = pd.DataFrame({
        "code_magasin": codes,
        "nom_magasin": codes,
        "ville": codes,
        "region": "",
        "flagship": False,
        "type_magasin": np.where(codes.str.upper().isin(WEB_NAMES), "WEB", "STANDARD"),
        "actif": True,
        "priorite": 0.0,
    })

    picking = load_reassort(reassort_xlsx) if reassort_xlsx else pd.DataFrame()

    # designation produit (best-effort) : si un des fichiers fournit un libelle,
    # on construit une carte reference -> designation pour enrichir l'affichage
    # (bons de prepa magasin). Absente si les exports n'ont pas la colonne.
    _DESIG_COLS = ("designation", "désignation", "desig", "libelle", "libellé",
                   "description", "designation article", "nom article", "designation1")
    designation_map: Dict[str, str] = {}
    for raw, refser in ((vraw, vref), (sraw, sref)):
        col = next((c for c in raw.columns
                    if str(c).strip().lower() in _DESIG_COLS), None)
        if not col:
            continue
        d = pd.DataFrame({"ref": list(refser.values),
                          "d": raw[col].astype(str).str.strip().values})
        d = d[(d["d"] != "") & (d["d"].str.lower() != "nan")]
        for ref, des in zip(d["ref"], d["d"]):
            designation_map.setdefault(str(ref), des)

    # carte (reference, couleur) -> marque : portee sur chaque transfert pour
    # l'affichage et le REGROUPEMENT par marque des bons de prepa magasin.
    marque_map: Dict[tuple, str] = {}
    for df in (stocks, v):
        if df is None or getattr(df, "empty", True):
            continue
        if "reference" not in df.columns or "marque" not in df.columns:
            continue
        coul = df["couleur"] if "couleur" in df.columns else pd.Series([""] * len(df))
        # pandas 3 : astype(str) conserve NaN en float -> on stringifie a la main.
        for ref, c, mq in zip(df["reference"], coul, df["marque"]):
            mq = str(mq).strip()
            if mq and mq.lower() != "nan":
                marque_map.setdefault((str(ref), str(c)), mq)

    return {
        "stocks": stocks,
        "ventes": sales_out,
        "ventes_detail": v,          # ventes ligne a ligne avec date (mesure d'impact)
        "picking": picking,
        "magasins": stores,
        "historique": pd.DataFrame(),
        "designation_map": designation_map,
        "marque_map": marque_map,
    }
