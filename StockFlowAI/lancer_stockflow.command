#!/usr/bin/env bash
# StockFlow AI - mini-site local (macOS / Linux). Double-cliquez ce fichier
# (sur Mac : clic droit > Ouvrir la premiere fois).
cd "$(dirname "$0")" || exit 1
echo "Installation des dependances (premiere fois seulement)..."
python3 -m pip install --quiet -r requirements.txt
echo "Ouverture de StockFlow AI dans votre navigateur..."
python3 -m streamlit run app.py
