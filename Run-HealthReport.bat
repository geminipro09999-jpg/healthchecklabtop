@echo off
title Windows Laptop & PC Health Diagnostic & Auto-Sync
cd /d "%~dp0"

echo ================================================================
echo    Windows Laptop & PC Health Diagnostic & Auto-Sync
echo ================================================================
echo.

set comp=UNICOMTIC
set /p comp="Enter Client / Company Name [Press Enter for 'UNICOMTIC']: "
if "%comp%"=="" set comp=UNICOMTIC

set cust=
set /p cust="Enter Customer / User Name (e.g. Ramesh, Kamalanathan): "
if "%cust%"=="" set cust=%USERNAME%

set phone=
set /p phone="Enter Customer Phone [Optional]: "

set srv=https://healthchecklabtop.vercel.app
set /p srv="Enter Dashboard Server URL [Press Enter for 'https://healthchecklabtop.vercel.app']: "
if "%srv%"=="" set srv=https://healthchecklabtop.vercel.app

echo.
echo ================================================================
echo  Target Company   : %comp%
echo  Customer / User  : %cust%
echo  Dashboard Server : %srv%
echo ================================================================
echo.
echo [*] Scanning hardware specs and running diagnostics...
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Generate-HealthReport.ps1" -Company "%comp%" -CustomerName "%cust%" -CustomerPhone "%phone%" -ServerUrl "%srv%" -AutoUpload

echo.
echo ================================================================
echo  [D] Open Multi-Laptop Inventory Dashboard
echo  [E] Exit
echo ================================================================
set /p choice="Choose an option (D/E) [Default: D]: "
if /i "%choice%"=="E" goto end

start "" "%srv%/Dashboard.html"

:end
pause
