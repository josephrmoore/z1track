@echo off
REM Z1 Click Tracker launcher.
REM 1. In FCEUX: File > Lua > New Lua Script Window > run click_tracker.lua
REM 2. Double-click this file (or run: python click_tracker.py)
py click_tracker.py
if errorlevel 1 (
    python click_tracker.py
)
pause
