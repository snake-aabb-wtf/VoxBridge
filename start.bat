@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo VoxBridge virtual environment was not found.
    echo Create it and install dependencies by following README.md.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" "main.py"
if errorlevel 1 (
    echo.
    echo VoxBridge exited with an error. See the message above.
    pause
)

endlocal
