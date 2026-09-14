@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul
title Prism 决策工作台 · 一键启动
cd /d "%~dp0" || goto :project_dir_failed

set "VENV_DIR=%~dp0.venv"
set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"

echo ======================================================================
echo.
echo     ██████╗ ██████╗  ██╗███████╗███╗   ███╗
echo     ██╔══██╗██╔══██╗██║██╔════╝████╗ ████║
echo     ██████╔╝██████╔╝██║███████╗██╔████╔██║
echo     ██╔═══╝ ██╔══██╗██║╚════██║██║╚██╔╝██║
echo     ██║     ██║  ██║██║███████║██║ ╚═╝ ██║
echo     ╚═╝     ╚═╝  ╚═╝╚═╝╚══════╝╚═╝     ╚═╝
echo.
echo     Prism · 可解释个性化投资研究与决策支持工作台
echo ======================================================================
echo.

:: rapidocr-onnxruntime 仅支持 Python 3.11/3.12。首次运行自动创建隔离环境。
if not exist "%PYTHON_EXE%" (
    if exist "%VENV_DIR%\" goto :invalid_venv
    echo [环境] 未检测到 .venv，正在创建 Python 虚拟环境...
    call :create_venv
    if errorlevel 1 goto :python_not_found
)

"%PYTHON_EXE%" -c "import sys; raise SystemExit(0 if sys.version_info[:2] in ((3, 11), (3, 12)) else 1)" >nul 2>nul
if errorlevel 1 goto :unsupported_venv

echo [环境] 使用解释器: %PYTHON_EXE%
"%PYTHON_EXE%" -c "import fastapi, uvicorn, multipart, rapidocr_onnxruntime; from PIL import Image" >nul 2>nul
if errorlevel 1 (
    echo [依赖] 检测到缺失或不可用的运行依赖，正在安装: pip install -e ".[web]"
    "%PYTHON_EXE%" -m pip install -e ".[web]"
    if errorlevel 1 goto :dependency_failed
    "%PYTHON_EXE%" -c "import fastapi, uvicorn, multipart, rapidocr_onnxruntime; from PIL import Image" >nul 2>nul
    if errorlevel 1 goto :dependency_probe_failed
)

echo [PASS] Python 版本与运行依赖检查通过。
echo [就绪] 正在启动 Prism 决策工作台服务...
echo [地址] http://127.0.0.1:8000
echo [提示] 浏览器将自动打开，按 Ctrl+C 可终止服务。
echo ======================================================================
echo.

start "" cmd /c "timeout /t 2 /nobreak >nul && start http://127.0.0.1:8000"
"%PYTHON_EXE%" -m uvicorn app.api.main:app --host 127.0.0.1 --port 8000 --reload
if errorlevel 1 goto :server_failed
exit /b 0

:create_venv
where py >nul 2>nul
if not errorlevel 1 (
    py -3.12 -c "import sys" >nul 2>nul
    if not errorlevel 1 goto :create_with_python312
    py -3.11 -c "import sys" >nul 2>nul
    if not errorlevel 1 goto :create_with_python311
)

where python >nul 2>nul
if errorlevel 1 exit /b 1
python -c "import sys; raise SystemExit(0 if sys.version_info[:2] in ((3, 11), (3, 12)) else 1)" >nul 2>nul
if errorlevel 1 exit /b 1
python -m venv "%VENV_DIR%"
if errorlevel 1 exit /b 1
exit /b 0

:create_with_python312
py -3.12 -m venv "%VENV_DIR%"
if errorlevel 1 exit /b 1
exit /b 0

:create_with_python311
py -3.11 -m venv "%VENV_DIR%"
if errorlevel 1 exit /b 1
exit /b 0

:project_dir_failed
echo [FAIL] 无法进入 Prism 项目目录。
goto :failed

:invalid_venv
echo [FAIL] .venv 目录存在，但其中没有可用的 Python 解释器。
echo [INFO] 请移走损坏的 .venv 目录后重新运行 start.bat。
goto :failed

:python_not_found
echo [FAIL] 未检测到兼容的 Python 解释器。
echo [INFO] 请安装 64 位 Python 3.12 或 3.11，然后重新运行 start.bat。
goto :failed

:unsupported_venv
echo [FAIL] 当前 .venv 不是 Python 3.11 或 3.12，OCR 运行依赖不支持该版本。
echo [INFO] 请移走现有 .venv 目录后重新运行 start.bat。
goto :failed

:dependency_failed
echo [FAIL] 依赖安装失败。上方 pip 输出包含实际失败原因。
echo [INFO] 可手动重试: .venv\Scripts\python -m pip install -e ".[web]"
goto :failed

:dependency_probe_failed
echo [FAIL] pip 已结束，但完整运行依赖导入检查仍未通过。
echo [INFO] 可手动诊断: .venv\Scripts\python -c "import fastapi, uvicorn, multipart, rapidocr_onnxruntime; from PIL import Image"
goto :failed

:server_failed
echo [FAIL] Prism 服务异常退出，请检查上方日志。

:failed
echo.
pause
exit /b 1
