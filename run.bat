@echo off
rem Bode plotter launcher (SPEC.md section 5). Idempotent; extra arguments go to the app.
setlocal enabledelayedexpansion
cd /d "%~dp0"

set "PY="
for %%V in (3.14 3.13 3.12 3.11) do (
    if not defined PY (
        py -%%V -c "import sys" >nul 2>nul && set "PY=py -%%V"
    )
)
if not defined PY (
    python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul && set "PY=python"
)
if not defined PY (
    echo [run.bat] Step failed: no Python 3.11 or newer found.
    echo           Install it from https://www.python.org/downloads/ ^(tick "py launcher"^), then run this again.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo [run.bat] Creating .venv ...
    %PY% -m venv .venv || (echo [run.bat] Step failed: creating the virtual environment. & pause & exit /b 1)
)

for /f "delims=" %%H in ('.venv\Scripts\python.exe -c "import hashlib,sys; print(hashlib.sha256(open('requirements.txt','rb').read()).hexdigest())"') do set "REQ_HASH=%%H"
set "OLD_HASH="
if exist ".venv\.req_hash" set /p OLD_HASH=<".venv\.req_hash"
if not "%REQ_HASH%"=="%OLD_HASH%" (
    echo [run.bat] Installing requirements ...
    .venv\Scripts\python.exe -m pip install --upgrade pip || (echo [run.bat] Step failed: upgrading pip. & pause & exit /b 1)
    .venv\Scripts\python.exe -m pip install -r requirements.txt || (echo [run.bat] Step failed: installing requirements. & pause & exit /b 1)
    .venv\Scripts\python.exe -m pip install -e . || (echo [run.bat] Step failed: installing the app. & pause & exit /b 1)
    >".venv\.req_hash" echo %REQ_HASH%
)

.venv\Scripts\python.exe -m bodeplot %*
if errorlevel 1 (
    echo [run.bat] Step failed: the app exited with an error.
    pause
    exit /b 1
)
