@echo off
REM StockFlow AI - mini-site local (Windows). Double-cliquez ce fichier.
cd /d "%~dp0"
echo Installation des dependances (premiere fois seulement)...
python -m pip install --quiet -r requirements.txt
echo Ouverture de StockFlow AI dans votre navigateur...
python -m streamlit run app.py
pause
