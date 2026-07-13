import pandas as pd
from stockflow.parameters import Parameters, classer_score


def test_defaults_presents():
    p = Parameters()
    assert p.get("couverture_cible_magasin") == 30
    assert p.get("couverture_min_expediteur") == 20
    assert p.get("nb_max_destinations") == 4


def test_tailles_coeur_par_categorie():
    p = Parameters()
    assert p.tailles_coeur_for("TEXTILE_HOMME") == ["S", "M", "L"]
    # categorie inconnue -> defaut
    assert p.tailles_coeur_for("INCONNUE") == ["S", "M", "L"]
    assert p.tailles_coeur_for(None) == ["S", "M", "L"]


def test_classer_score():
    assert classer_score(95) == "Prioritaire"
    assert classer_score(85) == "Fortement recommande"
    assert classer_score(75) == "Recommande"
    assert classer_score(65) == "A valider"
    assert classer_score(50) == "Non retenu"


def test_load_from_xlsx(tmp_path):
    path = tmp_path / "parametres.xlsx"
    df = pd.DataFrame({"cle": ["couverture_cible_magasin", "nb_max_destinations"],
                       "valeur": [40, 3]})
    with pd.ExcelWriter(path) as w:
        df.to_excel(w, sheet_name="parametres", index=False)
    p = Parameters.load(path)
    assert p.get("couverture_cible_magasin") == 40
    assert p.get("nb_max_destinations") == 3
    # les autres defauts restent
    assert p.get("couverture_min_expediteur") == 20


def test_absence_fichier_ne_bloque_pas(tmp_path):
    p = Parameters.load(tmp_path / "inexistant.xlsx")
    assert p.get("couverture_cible_magasin") == 30
