@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

set "GPU_FLAG=--gpu"
set "BUILD_FLAG="
set "FORWARD_ARGS="

:parse_args
if "%~1"=="" goto done_args
if /I "%~1"=="--no-gpu" (
    set "GPU_FLAG="
    shift
    goto parse_args
)
if /I "%~1"=="--build" (
    set "BUILD_FLAG=--build"
    shift
    goto parse_args
)
set "FORWARD_ARGS=%FORWARD_ARGS% "%~1""
shift
goto parse_args

:done_args

echo Generating Docker overrides...
if defined GPU_FLAG (
    python prepare_docker_release.py %GPU_FLAG%
) else (
    python prepare_docker_release.py
)
if errorlevel 1 exit /b %errorlevel%

echo Starting Docker stack...
if defined BUILD_FLAG (
    docker compose -f docker-compose.yml -f .docker/docker-compose.generated.yml up --build %FORWARD_ARGS%
) else (
    docker compose -f docker-compose.yml -f .docker/docker-compose.generated.yml up %FORWARD_ARGS%
)
