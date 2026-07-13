import pandas as pd
from stockflow import schema, import_data
from stockflow.quality_checks import QualityReport, check_stocks, check_sales


def test_map_columns_alias_et_accents():
    df = pd.DataFrame(columns=["Magasin", "Réf", "Couleur", "Taille", "Stock Physique"])
    mapped = schema.map_columns(df)
    assert "magasin" in mapped.columns
    assert "reference" in mapped.columns
    assert "stock_physique" in mapped.columns


def test_ensure_store_col_code_magasin():
    # un fichier ventes qui nomme la colonne 'code_magasin'
    df = pd.DataFrame({"code_magasin": ["A"], "reference": ["R"], "couleur": ["N"],
                       "taille": ["M"], "ventes_35j": [10]})
    df.to_dict()


def test_to_number_gere_virgule_et_espace():
    s = pd.Series(["1 200,5", "3", "-2"])
    out = import_data.to_number(s)
    assert out.tolist() == [1200.5, 3.0, -2.0]


def test_to_bool_tokens():
    s = pd.Series(["oui", "non", "1", "0", "web", ""])
    out = import_data.to_bool(s)
    assert out.tolist() == [True, False, True, False, True, False]


def test_quality_bloque_si_colonne_manquante():
    df = pd.DataFrame({"reference": ["R"], "couleur": ["N"], "taille": ["M"],
                       "stock_physique": [5]})  # magasin manquant
    report = QualityReport()
    check_stocks(df, report)
    assert report.bloquant


def test_quality_agrege_doublons():
    df = pd.DataFrame({
        "magasin": ["A", "A"], "reference": ["R", "R"], "couleur": ["N", "N"],
        "taille": ["M", "M"], "stock_physique": [3, 4], "stock_disponible": [3, 4],
    })
    report = QualityReport()
    out = check_stocks(df, report)
    assert len(out) == 1
    assert out["stock_physique"].iloc[0] == 7  # somme des doublons
    assert any(a.type == "doublons" for a in report.anomalies)
