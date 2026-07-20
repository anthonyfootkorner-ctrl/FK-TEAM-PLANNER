"""Push résilient : une colonne absente de la table (migration SQL oubliée) ne
doit plus faire échouer tout le run — on retire la colonne et on réessaie.

Reproduit le cas réel : la colonne `designation` n'avait pas été ajoutée à
`stockflow_transfers`, et PostgREST renvoyait 400 PGRST204, ce qui plantait
l'insertion des transferts (donc aussi le réassort central et l'e-mail).
"""

from __future__ import annotations

import json

import pytest
import requests

from stockflow import push_supabase as ps


class _Resp:
    def __init__(self, status, body=None, text=""):
        self.status_code = status
        self._body = body
        self.text = text

    def json(self):
        if self._body is None:
            raise ValueError("no json")
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


def test_post_rows_retire_colonne_absente(monkeypatch):
    calls = []

    def fake_post(url, headers=None, data=None, timeout=None):
        payload = json.loads(data)
        calls.append(payload)
        if any("designation" in r for r in payload):
            return _Resp(400, {
                "code": "PGRST204",
                "message": "Could not find the 'designation' column of "
                           "'stockflow_transfers' in the schema cache",
                "details": None, "hint": None})
        return _Resp(201)

    monkeypatch.setattr(requests, "post", fake_post)
    rows = [{"reference": "R1", "designation": "T-SHIRT", "quantite": 1},
            {"reference": "R2", "designation": None, "quantite": 2}]
    resp = ps._post_rows("http://x/stockflow_transfers", {}, rows, timeout=10)

    assert resp.status_code == 201
    assert len(calls) == 2                              # 1 échec + 1 réussite
    assert all("designation" not in r for r in calls[-1])   # colonne retirée
    assert all("reference" in r for r in calls[-1])         # le reste conservé


def test_clean_neutralise_nan_inf():
    rows = [{"a": float("nan"), "b": "x", "c": 3},
            {"a": float("inf"), "b": float("-inf"), "c": None}]
    out = ps._clean(rows)
    assert out[0]["a"] is None and out[0]["b"] == "x" and out[0]["c"] == 3
    assert out[1]["a"] is None and out[1]["b"] is None
    # et le résultat est sérialisable en JSON strict (comme l'exige Supabase)
    json.dumps(out, allow_nan=False)


def test_post_rows_erreur_non_colonne_leve(monkeypatch):
    """Une vraie erreur (pas une colonne manquante) doit toujours remonter."""
    def fake_post(url, headers=None, data=None, timeout=None):
        return _Resp(401, {"message": "JWT expired"})

    monkeypatch.setattr(requests, "post", fake_post)
    with pytest.raises(requests.HTTPError):
        ps._post_rows("http://x/stockflow_transfers", {}, [{"a": 1}], timeout=10)
