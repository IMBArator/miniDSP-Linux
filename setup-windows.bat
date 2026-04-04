@echo off
setlocal

set PY_VERSION=3.13.3
set PY_MAJOR=313
set PY_DIR=python-embed
set PY_ZIP=python-%PY_VERSION%-embed-amd64.zip
set PY_URL=https://www.python.org/ftp/python/%PY_VERSION%/%PY_ZIP%
set PTH_FILE=%PY_DIR%\python%PY_MAJOR%._pth

echo === Setting up portable Python %PY_VERSION% for DSP 4x4 Mini tools ===
echo.

:: Download embedded Python
echo Downloading Python %PY_VERSION% embedded...
curl -L -o "%PY_ZIP%" "%PY_URL%"
if %errorlevel% neq 0 (
    echo ERROR: Download failed.
    exit /b 1
)

:: Extract
echo Extracting to %PY_DIR%...
if exist "%PY_DIR%" rmdir /s /q "%PY_DIR%"
powershell -Command "Expand-Archive -Path '%PY_ZIP%' -DestinationPath '%PY_DIR%' -Force"
del "%PY_ZIP%"

:: Enable import site (required for pip to work with embedded Python)
echo Enabling import site in %PTH_FILE%...
powershell -Command "(Get-Content '%PTH_FILE%') -replace '^#import site','import site' | Set-Content '%PTH_FILE%'"

:: Download and run get-pip.py
echo Downloading get-pip.py...
curl -L -o "%PY_DIR%\get-pip.py" "https://bootstrap.pypa.io/get-pip.py"
if %errorlevel% neq 0 (
    echo ERROR: get-pip.py download failed.
    exit /b 1
)

echo Installing pip...
%PY_DIR%\python.exe %PY_DIR%\get-pip.py --no-warn-script-location
if %errorlevel% neq 0 (
    echo ERROR: pip installation failed.
    exit /b 1
)
del "%PY_DIR%\get-pip.py"

:: Install setuptools (needed as build backend)
echo Installing setuptools...
%PY_DIR%\python.exe -m pip install --no-warn-script-location setuptools
if %errorlevel% neq 0 (
    echo ERROR: setuptools installation failed.
    exit /b 1
)

:: Install the project
echo Installing minidsp-linux project...
%PY_DIR%\python.exe -m pip install --no-warn-script-location .
if %errorlevel% neq 0 (
    echo ERROR: Project installation failed.
    exit /b 1
)

echo.
echo === Setup complete ===
echo.
echo Usage:
echo   %PY_DIR%\python.exe -m dspanalyze --help
echo   %PY_DIR%\python.exe -m dspanalyze capture --help
echo   %PY_DIR%\python.exe -m minidsp --help
