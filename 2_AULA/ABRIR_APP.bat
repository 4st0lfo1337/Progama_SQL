@echo off
cd /d "%~dp0"
title Secretaria Digital
where py >nul 2>nul
if %errorlevel%==0 (py secretaria_digital.py) else (python secretaria_digital.py)
pause
