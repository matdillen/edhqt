@echo off
python -m app.main
if %errorlevel% neq 0 (
    echo.
    echo ---------------------------------------
    echo Script crashed with error code %errorlevel%
    echo ---------------------------------------
    pause
)