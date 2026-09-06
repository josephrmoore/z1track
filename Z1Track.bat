@echo off
REM Z1TRack launcher -- double-click this file to start.
REM Keeps this window open after exit (success or failure) so any message
REM is actually readable, instead of the console flashing and closing.

cd /d "%~dp0"

where py >nul 2>nul
if %ERRORLEVEL%==0 (
    py run.py
) else (
    where python >nul 2>nul
    if %ERRORLEVEL%==0 (
        python run.py
    ) else (
        echo Could not find Python. Install Python 3 from https://python.org/downloads/
        echo ^(make sure to check "Add python.exe to PATH" during install^)
    )
)

echo.
pause
