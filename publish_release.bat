@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

if "%~1"=="" goto usage_error

set "TAG="
set "PUSH_LATEST=0"

:parse_args
if "%~1"=="" goto parsed
if /I "%~1"=="--latest" (
    set "PUSH_LATEST=1"
    shift
    goto parse_args
)
if /I "%~1"=="--help" goto usage_ok
if /I "%~1"=="-h" goto usage_ok
if defined TAG (
    echo Error: unexpected argument: %~1
    goto usage_error
)
set "TAG=%~1"
shift
goto parse_args

:parsed
where docker >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo Error: docker is not installed or not in PATH.
    exit /b 1
)

where gh >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo Error: gh is not installed or not in PATH.
    exit /b 1
)

if not defined REGISTRY set "REGISTRY=ghcr.io"
if not defined IMAGE_NAMESPACE set "IMAGE_NAMESPACE=ekkusuu"
if not defined BACKEND_IMAGE set "BACKEND_IMAGE=project-metis-backend"
if not defined LLM_IMAGE set "LLM_IMAGE=project-metis-llm-service"
if not defined TORCH_INDEX_URL set "TORCH_INDEX_URL=https://download.pytorch.org/whl/cu126"
if not defined GITHUB_REPOSITORY set "GITHUB_REPOSITORY=Ekkusuu/project-metis"

set "BACKEND_REF=%REGISTRY%/%IMAGE_NAMESPACE%/%BACKEND_IMAGE%:%TAG%"
set "LLM_REF=%REGISTRY%/%IMAGE_NAMESPACE%/%LLM_IMAGE%:%TAG%"
set "RELEASE_DIR=.release\%TAG%"
set "BUNDLE_DIR=%RELEASE_DIR%\project-metis-%TAG%"
set "RELEASE_COMPOSE=%BUNDLE_DIR%\docker-compose.yml"
set "RELEASE_GPU_COMPOSE=%BUNDLE_DIR%\docker-compose.gpu.yml"
set "RELEASE_CONFIG=%BUNDLE_DIR%\config.local.example.yaml"
set "RELEASE_NOTES=%BUNDLE_DIR%\RELEASE.md"
set "RELEASE_ZIP=%RELEASE_DIR%\project-metis-%TAG%.zip"
set "RELEASE_ASSET=%RELEASE_DIR%\project-metis-release.zip"

echo Publishing Docker release %TAG%
echo Backend image: %BACKEND_REF%
echo LLM image: %LLM_REF%
echo.

docker build --build-arg "TORCH_INDEX_URL=%TORCH_INDEX_URL%" -f backend/Dockerfile -t "%BACKEND_REF%" .
if %ERRORLEVEL% NEQ 0 exit /b %ERRORLEVEL%

docker build -f backend\llm_service\Dockerfile -t "%LLM_REF%" .
if %ERRORLEVEL% NEQ 0 exit /b %ERRORLEVEL%

docker push "%BACKEND_REF%"
if %ERRORLEVEL% NEQ 0 exit /b %ERRORLEVEL%

docker push "%LLM_REF%"
if %ERRORLEVEL% NEQ 0 exit /b %ERRORLEVEL%

if "%PUSH_LATEST%"=="1" (
    set "BACKEND_LATEST=%REGISTRY%/%IMAGE_NAMESPACE%/%BACKEND_IMAGE%:latest"
    set "LLM_LATEST=%REGISTRY%/%IMAGE_NAMESPACE%/%LLM_IMAGE%:latest"

    docker tag "%BACKEND_REF%" "!BACKEND_LATEST!"
    if %ERRORLEVEL% NEQ 0 exit /b %ERRORLEVEL%
    docker tag "%LLM_REF%" "!LLM_LATEST!"
    if %ERRORLEVEL% NEQ 0 exit /b %ERRORLEVEL%

    docker push "!BACKEND_LATEST!"
    if %ERRORLEVEL% NEQ 0 exit /b %ERRORLEVEL%
    docker push "!LLM_LATEST!"
    if %ERRORLEVEL% NEQ 0 exit /b %ERRORLEVEL%
)

if not exist "%BUNDLE_DIR%" mkdir "%BUNDLE_DIR%"
if not exist "%BUNDLE_DIR%\model" mkdir "%BUNDLE_DIR%\model"
if not exist "%BUNDLE_DIR%\rag-models" mkdir "%BUNDLE_DIR%\rag-models"
if not exist "%BUNDLE_DIR%\memory" mkdir "%BUNDLE_DIR%\memory"
if not exist "%BUNDLE_DIR%\docs" mkdir "%BUNDLE_DIR%\docs"
if not exist "%BUNDLE_DIR%\.chromadb" mkdir "%BUNDLE_DIR%\.chromadb"

copy /Y "config.yaml" "%BUNDLE_DIR%\config.yaml" >nul
type nul > "%BUNDLE_DIR%\model\.gitkeep"
type nul > "%BUNDLE_DIR%\rag-models\.gitkeep"
type nul > "%BUNDLE_DIR%\memory\.gitkeep"
type nul > "%BUNDLE_DIR%\docs\.gitkeep"
type nul > "%BUNDLE_DIR%\.chromadb\.gitkeep"

(
echo services:
echo   llm_service:
echo     image: %LLM_REF%
echo     restart: unless-stopped
echo     volumes:
echo       - ./config.yaml:/app/config.yaml:ro
echo       - ./model:/app/model:ro
echo     healthcheck:
echo       test: ["CMD", "node", "-e", "fetch('http://127.0.0.1:3000/health').then((res) =^> { if (!res.ok) process.exit(1); }).catch(() =^> process.exit(1));"]
echo       interval: 30s
echo       timeout: 10s
echo       retries: 10
echo       start_period: 300s
echo.
echo   backend:
echo     image: %BACKEND_REF%
echo     restart: unless-stopped
echo     depends_on:
echo       - llm_service
echo     environment:
echo       METIS_LLM_SERVICE_HOST: llm_service
echo       METIS_LLM_SERVICE_PORT: 3000
echo     ports:
echo       - "8000:8000"
echo     volumes:
echo       - ./config.yaml:/app/config.yaml:ro
echo       - ./model:/app/model:ro
echo       - ./rag-models:/app/rag-models:ro
echo       - ./memory:/app/memory
echo       - ./.chromadb:/app/.chromadb
echo       - ./docs:/app/docs:ro
echo     healthcheck:
echo       test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=5)"]
echo       interval: 30s
echo       timeout: 10s
echo       retries: 5
echo       start_period: 90s
) > "%RELEASE_COMPOSE%"

(
echo services:
echo   llm_service:
echo     environment:
echo       METIS_LLM_GPU: cuda
echo       NVIDIA_VISIBLE_DEVICES: all
echo       NVIDIA_DRIVER_CAPABILITIES: compute,utility
echo     deploy:
echo       resources:
echo         reservations:
echo           devices:
echo             - driver: nvidia
echo               count: all
echo               capabilities: [gpu]
echo.
echo   backend:
echo     environment:
echo       NVIDIA_VISIBLE_DEVICES: all
echo       NVIDIA_DRIVER_CAPABILITIES: compute,utility
echo     deploy:
echo       resources:
echo         reservations:
echo           devices:
echo             - driver: nvidia
echo               count: all
echo               capabilities: [gpu]
) > "%RELEASE_GPU_COMPOSE%"

(
echo # Local overrides for the release bundle.
echo # Keep indexed folders inside this extracted release directory unless you also
echo # add matching bind mounts to docker-compose.yml.
echo.
echo rag:
echo   folders_to_index:
echo     - "docs"
echo     - "memory/long_term"
echo.
echo chat:
echo   system_prompt: ^>
echo     You are Metis, a helpful AI assistant.
echo     Keep responses concise, accurate, and empathetic.
) > "%RELEASE_CONFIG%"

(
echo # Project Metis %TAG%
echo.
echo ## Quick Start
echo.
echo 1. Put your GGUF model file in `model/`
echo 2. Put embedding and reranker model folders in `rag-models/`
echo 3. Copy `config.local.example.yaml` to `config.local.yaml` if you need local overrides
echo    and keep `rag.folders_to_index` inside this release folder by default
echo 4. For standard startup, run:
echo.
echo ```sh
echo docker compose up
echo ```
echo.
echo 5. For GPU-enabled startup, run:
echo.
echo ```sh
echo docker compose -f docker-compose.yml -f docker-compose.gpu.yml up
echo ```
echo.
echo 6. Open `http://localhost:8000`
echo.
echo ## Notes
echo.
echo - `config.yaml` is included in this bundle
echo - model and embedding files are not included; add your own locally
echo - `memory/`, `docs/`, and `.chromadb/` are included as local data folders
echo - `docker-compose.gpu.yml` is included for NVIDIA Docker setups
echo - `config.local.example.yaml` defaults RAG indexing to `docs` and `memory/long_term`
echo.
echo ## Published Images
echo.
echo - %BACKEND_REF%
echo - %LLM_REF%
) > "%RELEASE_NOTES%"

powershell -NoProfile -Command "Compress-Archive -Path '%BUNDLE_DIR%' -DestinationPath '%RELEASE_ZIP%' -Force"
if %ERRORLEVEL% NEQ 0 exit /b %ERRORLEVEL%

copy /Y "%RELEASE_ZIP%" "%RELEASE_ASSET%" >nul
if %ERRORLEVEL% NEQ 0 exit /b %ERRORLEVEL%

gh release view "%TAG%" --repo "%GITHUB_REPOSITORY%" >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    gh release upload "%TAG%" "%RELEASE_ASSET%" --clobber --repo "%GITHUB_REPOSITORY%"
    if %ERRORLEVEL% NEQ 0 exit /b %ERRORLEVEL%
) else (
    gh release create "%TAG%" "%RELEASE_ASSET%" --repo "%GITHUB_REPOSITORY%" --title "%TAG%" --notes "Docker release %TAG%"
    if %ERRORLEVEL% NEQ 0 exit /b %ERRORLEVEL%
)

echo.
echo Published successfully.
echo GitHub release: https://github.com/%GITHUB_REPOSITORY%/releases/tag/%TAG%
exit /b 0

:usage_ok
echo Usage: publish_release.bat ^<tag^> [--latest]
echo.
echo Environment overrides:
echo   REGISTRY           Docker registry ^(default: ghcr.io^)
echo   IMAGE_NAMESPACE    Image namespace ^(default: ekkusuu^)
echo   BACKEND_IMAGE      Backend image name ^(default: project-metis-backend^)
echo   LLM_IMAGE          LLM image name ^(default: project-metis-llm-service^)
echo   TORCH_INDEX_URL    Backend Docker build arg for PyTorch wheels
echo   GITHUB_REPOSITORY  GitHub repo for the release ^(default: Ekkusuu/project-metis^)
exit /b 0

:usage_error
echo Usage: publish_release.bat ^<tag^> [--latest]
exit /b 1
