@echo off
cd /d "%~dp0"
echo Isto apaga as alteracoes da turma e recria o escola.db. & pause
where py >nul 2>nul
if %errorlevel%==0 (py criar_banco.py) else (python criar_banco.py)
pause
