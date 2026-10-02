@echo off
rem Sobe o CFTV Agent (API + painel na mesma porta) e abre o navegador quando a API responder.
cd /d "%~dp0"

if not exist "dashboard\dist\index.html" (
  echo Painel sem build. Gerando...
  pushd dashboard && call npm run build && popd
)

powershell -NoProfile -Command "try { Invoke-RestMethod http://127.0.0.1:8000/health -TimeoutSec 2 | Out-Null; exit 0 } catch { exit 1 }"
if errorlevel 1 (
  start "CFTV Agent - API" venv\Scripts\python.exe backend\main.py
) else (
  echo API ja estava no ar.
)

powershell -NoProfile -Command "for ($i = 0; $i -lt 40; $i++) { try { Invoke-RestMethod http://127.0.0.1:8000/health -TimeoutSec 2 | Out-Null; exit 0 } catch { Start-Sleep -Milliseconds 500 } }; exit 1"
if errorlevel 1 (
  echo A API nao respondeu em 20 s. Veja a janela "CFTV Agent - API".
  pause
  exit /b 1
)
start "" http://127.0.0.1:8000
