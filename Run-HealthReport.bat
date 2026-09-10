@echo off
title Laptop Hardware Diagnostic and Cloud Auto-Sync

:: -----------------------------------------------------------
:: Auto-Elevate to Administrator for Deep Hardware & Battery Access
:: -----------------------------------------------------------
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo.
    echo [*] Requesting Administrator privileges for deep hardware & battery diagnostics...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -Verb RunAs" >nul 2>&1
    if %errorLevel% equ 0 exit /b
    echo [*] Continuing in standard user mode...
)

cd /d "%~dp0"

echo ================================================================
echo    Laptop Hardware Diagnostic and Cloud Auto-Sync
echo ================================================================
echo.

set comp=UNICOMTIC
set user_name=%USERNAME%
set user_phone=
set srv=https://healthchecklabtop.vercel.app

:: Auto-detect if local dashboard server is running on port 8080
powershell -NoProfile -Command "try { `$r = Invoke-WebRequest -Uri 'http://localhost:8080/api/server-info' -TimeoutSec 1 -UseBasicParsing; exit 0 } catch { exit 1 }" >nul 2>&1
if %errorLevel% equ 0 (
    set srv=http://localhost:8080
    echo [*] Detected Active Local Server on port 8080!
)

if not "%~1"=="" set comp=%~1
if not "%~2"=="" set user_name=%~2
if not "%~3"=="" set user_phone=%~3
if not "%~4"=="" set srv=%~4

if "%~1"=="" (
    echo [*] Target Company : %comp%
    echo [*] Target User    : %user_name%
    echo [*] Target Server  : %srv%
    echo.
    echo [*] Auto-Scan starting in 3 seconds... (Press C to customize info, or any key to start now)
    choice /c CY /n /t 3 /d Y >nul 2>&1
    if errorlevel 2 goto start_scan
    if errorlevel 1 goto prompt_inputs
)
goto start_scan

:prompt_inputs
echo.
set /p comp="Enter Company Name [Press Enter for '%comp%']: "
if "%comp%"=="" set comp=UNICOMTIC

set /p user_name="Enter User Name [Press Enter for '%USERNAME%']: "
if "%user_name%"=="" set user_name=%USERNAME%

set /p user_phone="Enter Customer Phone [Optional]: "

set /p srv="Enter Dashboard Server URL [Press Enter for '%srv%']: "
if "%srv%"=="" (
    powershell -NoProfile -Command "try { `$r = Invoke-WebRequest -Uri 'http://localhost:8080/api/server-info' -TimeoutSec 1 -UseBasicParsing; exit 0 } catch { exit 1 }" >nul 2>&1
    if %errorLevel% equ 0 (
        set srv=http://localhost:8080
    ) else (
        set srv=https://healthchecklabtop.vercel.app
    )
)

:start_scan
echo.
echo ================================================================
echo  Target Company   : %comp%
echo  User Name        : %user_name%
if not "%user_phone%"=="" echo  Customer Phone  : %user_phone%
echo  Dashboard Server : %srv%
echo  Auto-Upload      : ENABLED (Immediate Cloud & Drive Sync)
echo ================================================================
echo.

if not exist "%~dp0Generate-HealthReport.ps1" (
    echo [*] Downloading diagnostic engine from GitHub...
    powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; try { (New-Object System.Net.WebClient).DownloadFile('https://raw.githubusercontent.com/geminipro09999-jpg/healthchecklabtop/main/Generate-HealthReport.ps1', '%~dp0Generate-HealthReport.ps1'); Write-Host '[+] Diagnostic engine downloaded successfully.' -ForegroundColor Green } catch { Write-Host '[-] Download failed: ' $_.Exception.Message -ForegroundColor Red }"
)

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
