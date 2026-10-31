@echo off
title Reel bot
cd /d "%~dp0"
:loop
python -u src\bot.py
echo Bot exited, restarting in 10s...
timeout /t 10 /nobreak >nul
goto loop
