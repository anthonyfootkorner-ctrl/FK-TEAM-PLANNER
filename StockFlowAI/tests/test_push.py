"""Test du constructeur de payload Supabase (hors ligne)."""

from types import SimpleNamespace

import pandas as pd

from stockflow.push_supabase import build_payload, dry_run


def _fake_result():
    sim = pd.DataFrame({
        "indicateur": ["ruptures", "score_sante_reseau"],
        "avant": [100.0, 48.0], "apres": [70.0, 53.0], "variation": [-30.0, 5.0],
    })
    transfers = pd.DataFrame({
        "priorite": ["Recommande", "A valider"], "score": [72.0, 63.0],
        "expediteur": ["A", "B"], "destinataire": ["C", "D"],
        "reference": ["779229-04", "IF2020-010"], "couleur": ["", ""],
        "taille": ["M", "L"], "quantite": [3, 1],
        "cov_dest_avant": [0, 5], "cov_dest_apres": [12, 15],
        "grille_avant": ["S", "M"], "grille_apres": ["S/M", "L/M"],
        "dispo_finale_dest": ["S:3 · M:3", "L:1 · M:2"],
        "picking_prevu": [0, 2], "motif": ["m1", "m2"],
    })
    return SimpleNamespace(simulation_global=sim, transfers=transfers)


def test_build_payload():
    meta = {"runid": "test", "perimetre": "24 magasins", "cible": 14,
            "marque_map": {("779229-04", ""): "NIKE"}}
    run, transfers = build_payload(_fake_result(), meta)
    assert run["nb_transferts"] == 2
    assert run["cible"] == 14
    assert run["kpis"]["ruptures"] == {"avant": 100, "apres": 70}
    # trie par score : le premier est le score le plus haut
    assert transfers[0]["n"] == 1 and transfers[0]["score"] == 72
    assert transfers[0]["marque"] == "NIKE"          # marque jointe
    assert transfers[0]["reference"] == "779229-04"  # code-barre complet
    assert transfers[0]["dispo_finale"] == "S:3 · M:3"


def test_dry_run(tmp_path):
    out = tmp_path / "payload.json"
    info = dry_run(_fake_result(), {"runid": "t", "cible": 14}, out)
    assert out.exists() and info["nb_transferts"] == 2
    import json
    data = json.loads(out.read_text(encoding="utf-8"))
    assert "run" in data and "transfers" in data and len(data["transfers"]) == 2
