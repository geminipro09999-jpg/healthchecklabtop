@echo off
title Laptop Fleet Health Dashboard
cd /d "%~dp0"

echo [*] Checking local dashboard server...
powershell -NoProfile -Command "try { `$r = Invoke-WebRequest -Uri 'http://localhost:8080/api/server-info' -TimeoutSec 1 -UseBasicParsing; exit 0 } catch { exit 1 }" >nul 2>&1
if %errorLevel% equ 0 (
    echo [*] Opening Local Dashboard at http://localhost:8080/Dashboard.html ...
    start "" "http://localhost:8080/Dashboard.html"
) else (
    echo [*] Local server not running. Starting local server...
    start "" cmd /c "%~dp0Start-Mobile-Server.bat"
    timeout /t 2 >nul
    start "" "http://localhost:8080/Dashboard.html"
)
timeout /t 2 >nul
