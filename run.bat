@echo off
cd /d %~dp0
if not exist .venv (
  echo First launch: creating the environment and installing libraries, this takes 2-4 minutes...
  python -m venv .venv
  .venv\Scripts\python.exe -m pip install -r requirements.txt
)
start "" http://localhost:8501
.venv\Scripts\python.exe -m streamlit run app.py --server.headless true
pause
