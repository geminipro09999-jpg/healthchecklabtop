@echo off
title Connect Google Drive Account
cd /d "%~dp0"

echo ================================================================
echo    Connecting Your Personal Google Drive Account
echo ================================================================
echo.
echo Your browser will open shortly to log into your Google Account.
echo.

python "%~dp0google_oauth_login.py"

echo.
pause
