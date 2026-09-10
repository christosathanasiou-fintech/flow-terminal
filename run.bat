@echo off
cd /d %~dp0
if not exist .venv (
  echo Πρωτη εκκινηση: δημιουργια περιβαλλοντος και εγκατασταση βιβλιοθηκων...
  python -m venv .venv
  .venv\Scripts\python.exe -m pip install -r requirements.txt
)
start "" http://localhost:8501
.venv\Scripts\python.exe -m streamlit run app.py --server.headless true
pause
