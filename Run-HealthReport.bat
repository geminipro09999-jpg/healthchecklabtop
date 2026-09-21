@echo off
title Laptop Hardware Diagnostic and Cloud Auto-Sync

:: -----------------------------------------------------------
:: Auto-Elevate to Administrator for Deep Hardware & Battery Access
:: -----------------------------------------------------------
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo.
    echo [*] Requesting Administrator privileges for deep hardware and battery diagnostics...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -Verb RunAs" >nul 2>&1
    if %errorLevel% equ 0 exit /b
    echo [*] Continuing in standard user mode...
)

cd /d "%~dp0"

echo ================================================================
echo    Laptop Hardware Diagnostic and Cloud Auto-Sync
echo ================================================================
echo.

set comp=Unicom TIC
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

if not "%~1"=="" goto start_scan

:select_company
echo ----------------------------------------------------------------
echo  Select Company / Organization:
echo   [1] Unicom TIC
echo   [2] Unicomtic Incubator
echo   [3] UnicomSD
echo   [4] Custom / Other
echo ----------------------------------------------------------------
set comp_opt=1
set /p comp_opt="Choose Company (1/2/3/4) [Press Enter for 1]: "
set comp_opt=%comp_opt: =%
if "%comp_opt%"=="2" set comp=Unicomtic Incubator& goto enter_user
if "%comp_opt%"=="3" set comp=UnicomSD& goto enter_user
if "%comp_opt%"=="4" goto custom_company
set comp=Unicom TIC
goto enter_user

:custom_company
set /p comp="Enter Custom Company Name: "
if "%comp%"=="" set comp=Unicom TIC
goto enter_user

:enter_user
echo.
set /p user_name="Enter User Name [Press Enter for '%USERNAME%']: "
if "%user_name%"=="" set user_name=%USERNAME%

set /p user_phone="Enter Customer Phone [Optional - Press Enter to Skip]: "
goto start_scan

:start_scan
echo.
echo ================================================================
echo  Target Company   : %comp%
echo  User Name        : %user_name%
if not "%user_phone%"=="" echo  Customer Phone  : %user_phone%
echo  Dashboard Server : %srv%
echo  Auto-Upload      : ENABLED (Immediate Cloud and Drive Sync)
echo ================================================================
echo.

:: Always auto-sync latest diagnostic engine & SMART provider from GitHub
echo [*] Checking and synchronizing latest diagnostic engine from GitHub...
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; try { (New-Object System.Net.WebClient).DownloadFile('https://raw.githubusercontent.com/geminipro09999-jpg/healthchecklabtop/main/Generate-HealthReport.ps1', '%~dp0Generate-HealthReport.ps1'); (New-Object System.Net.WebClient).DownloadFile('https://raw.githubusercontent.com/geminipro09999-jpg/healthchecklabtop/main/disk_health_provider.py', '%~dp0disk_health_provider.py'); Write-Host '[+] Diagnostic engine & SMART provider up-to-date.' -ForegroundColor Green } catch { Write-Host '[-] Offline notice: Continuing with existing local diagnostic files.' -ForegroundColor DarkYellow }"

if not exist "%~dp0Generate-HealthReport.ps1" (
    echo.
    echo [-] ERROR: Generate-HealthReport.ps1 was not found in this folder!
    echo     Please copy both Run-HealthReport.bat and Generate-HealthReport.ps1 together.
    echo.
    pause
    exit /b 1
)

echo.
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
