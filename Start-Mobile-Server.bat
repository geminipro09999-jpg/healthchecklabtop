@echo off
title Laptop Dashboard - Mobile Phone Server
cd /d "%~dp0"

echo ================================================================
echo    Starting Laptop Dashboard Mobile Server...
echo ================================================================
echo.

python "%~dp0server.py"

pause
