@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -c "import sys; raise SystemExit(sys.version_info < (3, 9))" >nul 2>nul
  if not errorlevel 1 (
    ".venv\Scripts\python.exe" -m tools.product_demo --open %*
    goto :done
  )
)
py -3 -c "import sys; raise SystemExit(sys.version_info < (3, 9))" >nul 2>nul
if not errorlevel 1 (
  py -3 -m tools.product_demo --open %*
  goto :done
)
python -c "import sys; raise SystemExit(sys.version_info < (3, 9))" >nul 2>nul
if not errorlevel 1 (
  python -m tools.product_demo --open %*
  goto :done
)
echo Python 3.9 or newer is required. Install Python or restore the project virtual environment.
pause
exit /b 1
:done
set "demo_exit_code=%errorlevel%"
if errorlevel 1 pause
endlocal & exit /b %demo_exit_code%
