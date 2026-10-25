@echo off
rem One-click demo start: builds the frontend if needed and serves everything on :8000.
setlocal
cd /d "%~dp0"

if not exist backend\.venv (
  echo [setup] creating Python environment...
  py -3.12 -m venv backend\.venv || goto :error
  backend\.venv\Scripts\python -m pip install -q -r backend\requirements.txt || goto :error
)

if not exist frontend\node_modules (
  echo [setup] installing frontend packages...
  pushd frontend && call npm install --no-audit --no-fund && popd || goto :error
)

if not exist frontend\dist\index.html (
  echo [build] building frontend...
  pushd frontend && call npm run build && popd || goto :error
)

echo.
echo  Cencia AI demo:  http://localhost:8000
echo  Phone remote:    http://YOUR-LAPTOP-IP:8000/demo   (same Wi-Fi; find the IP with: ipconfig)
echo.
cd backend
.venv\Scripts\python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
goto :eof

:error
echo Setup failed. See the messages above.
exit /b 1
