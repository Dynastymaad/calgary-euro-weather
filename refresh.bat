@echo off
cd /d "%~dp0"
python wx_web.py
if errorlevel 1 pause
