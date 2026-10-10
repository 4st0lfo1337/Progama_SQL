@echo off
cd /d "%~dp0"
title Verificar maquina
where py >nul 2>nul
if %errorlevel%==0 (py verificar_maquina.py) else (python verificar_maquina.py)
pause
