@echo off
title Reel Bot
chcp 65001 >nul
cd /d "%~dp0"
:loop
python -u src\bot.py
echo Bot exited, restarting in 10s...
ping -n 11 127.0.0.1 >nul
goto loop
