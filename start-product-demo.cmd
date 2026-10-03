@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -m tools.product_demo --port 8860
) else (
  py -3 -m tools.product_demo --port 8860
)
if errorlevel 1 pause
endlocal
