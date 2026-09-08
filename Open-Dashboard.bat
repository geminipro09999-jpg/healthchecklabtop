@echo off
title Laptop Fleet Health Dashboard
cd /d "%~dp0"

echo Opening Laptop Fleet Health Dashboard in your browser...
start "" "http://localhost:8080/Dashboard.html"

echo.
echo If the dashboard does not load, run Start-Mobile-Server.bat first.
timeout /t 3 >nul
