@echo off
python scripts\daily_integration_check.py
if errorlevel 1 exit /b %errorlevel%
