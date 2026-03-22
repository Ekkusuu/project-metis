@echo off
setlocal EnableExtensions

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

where python >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    set "PYTHON_BIN=python"
) else (
    py -3 --version >nul 2>nul
    if %ERRORLEVEL% EQU 0 (
        set "PYTHON_BIN=py -3"
    ) else (
        echo Error: Python is not installed or not in PATH.
        exit /b 1
    )
)

where npm >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo Error: npm is not installed or not in PATH.
    exit /b 1
)

if not defined TORCH_INDEX_URL set "TORCH_INDEX_URL=https://download.pytorch.org/whl/cu126"

echo Starting Project Metis setup...
echo.
echo Installing Python dependencies...
echo Using Python binary: %PYTHON_BIN%
echo TIP: Activate your virtual environment first if you use one.

call %PYTHON_BIN% -m pip install --upgrade pip
if %ERRORLEVEL% NEQ 0 (
    echo pip upgrade failed; continuing anyway...
)

call %PYTHON_BIN% -m pip install -r "%SCRIPT_DIR%requirements.txt"
if %ERRORLEVEL% NEQ 0 (
    set "PYTHON_ERR=%ERRORLEVEL%"
    goto after_python
)

call %PYTHON_BIN% -m pip uninstall -y torch torchvision torchaudio >nul 2>nul
call %PYTHON_BIN% -m pip install torch torchvision torchaudio --index-url "%TORCH_INDEX_URL%"
if %ERRORLEVEL% NEQ 0 (
    set "PYTHON_ERR=%ERRORLEVEL%"
    goto after_python
)

set "PYTHON_ERR=0"

:after_python
echo.
echo Installing Node dependencies...

call :install_node_dir "%SCRIPT_DIR%frontend" "Frontend"
if %ERRORLEVEL% NEQ 0 (
    set "NODE_ERR=%ERRORLEVEL%"
    goto summary
)

call :install_node_dir "%SCRIPT_DIR%backend\llm_service" "Backend LLM service"
if %ERRORLEVEL% NEQ 0 (
    set "NODE_ERR=%ERRORLEVEL%"
    goto summary
)

set "NODE_ERR=0"
goto summary

:install_node_dir
set "TARGET_DIR=%~1"
set "LABEL=%~2"

if not exist "%TARGET_DIR%" (
    echo %LABEL%: directory not found at %TARGET_DIR%
    exit /b 1
)

if exist "%TARGET_DIR%\package-lock.json" (
    echo %LABEL%: package-lock.json found, running npm ci
    pushd "%TARGET_DIR%"
    call npm ci
    set "CMD_ERR=%ERRORLEVEL%"
    popd
    exit /b %CMD_ERR%
) else (
    echo %LABEL%: running npm install
    pushd "%TARGET_DIR%"
    call npm install
    set "CMD_ERR=%ERRORLEVEL%"
    popd
    exit /b %CMD_ERR%
)

:summary
echo.
echo Summary:
if "%PYTHON_ERR%"=="0" (
    echo Python setup succeeded
) else (
    echo Python setup failed with exit code %PYTHON_ERR%
)

if "%NODE_ERR%"=="0" (
    echo Node setup succeeded
) else (
    echo Node setup failed with exit code %NODE_ERR%
)

if not "%PYTHON_ERR%"=="0" exit /b %PYTHON_ERR%
if not "%NODE_ERR%"=="0" exit /b %NODE_ERR%
exit /b 0
