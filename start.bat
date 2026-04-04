@echo off
setlocal EnableExtensions
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"
set "VENV_DIR=%SCRIPT_DIR%venv"

if not exist "%VENV_DIR%\Scripts\python.exe" (
  echo Error: virtual environment not found at %VENV_DIR%
  echo Run setup.bat first.
  exit /b 1
)

echo ============================================================
echo Starting Project Metis Services
echo ============================================================
echo.

REM Start the Node.js LLM service in a new window
echo Starting LLM Service (Node.js)...
start "Metis LLM Service" cmd /k "cd backend\llm_service && npm start"

REM Wait a bit for the LLM service to start
timeout /t 5 /nobreak

REM Start the Python backend
echo Starting FastAPI Backend (Python)...
start "Metis Backend" cmd /k call "%VENV_DIR%\Scripts\activate.bat" ^&^& uvicorn backend.main:app --reload

REM Wait a bit for the backend to start
timeout /t 3 /nobreak

REM Start the frontend dev server
echo Starting Frontend (Vite)...
start "Metis Frontend" cmd /k "cd frontend && npm run dev"

REM Open the app once all services are ready
echo Waiting for services to become ready and opening the app...
start "Metis Browser Launcher" /min cmd /c call "%VENV_DIR%\Scripts\activate.bat" ^&^& python open_when_ready.py --url http://localhost:5173 --wait-for http://localhost:3000/health --wait-for http://localhost:8000/health --wait-for http://localhost:5173 --timeout 300

echo.
echo ============================================================
echo All services started!
echo ============================================================
echo LLM Service: http://localhost:3000
echo Backend API: http://localhost:8000
echo Frontend: http://localhost:5173
echo ============================================================
echo.
echo Services are running in their own windows.
echo Close those windows individually when you want to stop them.
exit /b 0
