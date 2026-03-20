@echo off
cd /d "%~dp0"
python -m pip install -e . --quiet
python -m bot.main
echo Bot exited with code %ERRORLEVEL%
pause
