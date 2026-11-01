@echo off
title Reel bot
cd /d "%~dp0"
:loop
if not exist logs mkdir logs
python -u src\bot.py >> logs\bot_console.log 2>&1
echo Bot exited, restarting in 10s...
ping -n 11 127.0.0.1 >nul
goto loop
