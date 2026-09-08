@echo off
title Windows Laptop & PC Health Diagnostic
cd /d "%~dp0"

echo ================================================================
echo    Windows Laptop & PC Health Diagnostic Scanner
echo ================================================================
echo.

set comp=Unassigned / Retail
set /p comp="Enter Client / Company Name [Press Enter for 'Unassigned / Retail']: "

echo.
echo [*] Scanning hardware for client: %comp%...
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Generate-HealthReport.ps1" -Company "%comp%"

echo.
echo ================================================================
echo  [D] Open Multi-Laptop Inventory Dashboard
echo  [E] Exit
echo ================================================================
set /p choice="Choose an option (D/E) [Default: D]: "
if /i "%choice%"=="E" goto end

start "" "http://localhost:8080/Dashboard.html"

:end
