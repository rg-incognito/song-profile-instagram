@echo off
title Reel bot
cd /d "%~dp0"
:loop
if not exist logs mkdir logs
python -u src\bot.py >> logs\bot_console.log 2>&1
echo Bot exited, restarting in 10s...
timeout /t 10 /nobreak >nul
goto loop
