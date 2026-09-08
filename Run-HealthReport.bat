@echo off
title Laptop Hardware Diagnostic and Cloud Auto-Sync

:: -----------------------------------------------------------
:: Auto-Elevate to Administrator for Deep Hardware & Battery Access
:: -----------------------------------------------------------
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo.
    echo [*] Requesting Administrator privileges for deep hardware & battery diagnostics...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

cd /d "%~dp0"

echo ================================================================
echo    Laptop Hardware Diagnostic and Cloud Auto-Sync
echo ================================================================
echo.

set comp=UNICOMTIC
set /p comp="Enter Company Name [Press Enter for 'UNICOMTIC']: "
if "%comp%"=="" set comp=UNICOMTIC

set user_name=
set /p user_name="Enter User Name [Press Enter for '%USERNAME%']: "
if "%user_name%"=="" set user_name=%USERNAME%

set user_phone=
set /p user_phone="Enter Customer Phone [Optional]: "

set srv=https://healthchecklabtop.vercel.app
set /p srv="Enter Dashboard Server URL [Press Enter for 'https://healthchecklabtop.vercel.app']: "
if "%srv%"=="" set srv=https://healthchecklabtop.vercel.app

echo.
echo ================================================================
echo  Target Company   : %comp%
echo  User Name        : %user_name%
if not "%user_phone%"=="" echo  Customer Phone  : %user_phone%
echo  Dashboard Server : %srv%
echo ================================================================
echo.

echo [*] Synchronizing latest diagnostic engine from GitHub...
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; try { (New-Object System.Net.WebClient).DownloadFile('https://raw.githubusercontent.com/geminipro09999-jpg/healthchecklabtop/main/Generate-HealthReport.ps1', '%~dp0Generate-HealthReport.ps1'); Write-Host '[+] Latest diagnostic engine synchronized.' -ForegroundColor Green } catch { if (Test-Path '%~dp0Generate-HealthReport.ps1') { Write-Host '[!] Using local engine (offline mode).' -ForegroundColor Yellow } else { Write-Host '[-] Cloud download failed: ' $_.Exception.Message -ForegroundColor Red } }"

if not exist "%~dp0Generate-HealthReport.ps1" (
    echo.
    echo [-] ERROR: Generate-HealthReport.ps1 was not found in this folder!
    echo     Please copy both Run-HealthReport.bat and Generate-HealthReport.ps1 together.
    echo.
    pause
    exit /b 1
)

echo [*] Scanning hardware specs and running diagnostics...
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Generate-HealthReport.ps1" -Company "%comp%" -CustomerName "%user_name%" -CustomerPhone "%user_phone%" -ServerUrl "%srv%" -AutoUpload

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
