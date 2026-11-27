@echo off
setlocal

echo ============================================
echo SentiOH full local setup
echo ============================================

python -m pip install -r requirements.txt
if errorlevel 1 exit /b 1

echo.
echo Installing Chromium for the optional FSAI live refresh...
python -m playwright install chromium
if errorlevel 1 exit /b 1

echo.
echo Pulling local Llama 3.2 model...
ollama pull llama3.2:latest
if errorlevel 1 exit /b 1

echo.
echo Checking local Ollama...
python scripts\check_ollama.py
if errorlevel 1 exit /b 1

echo.
echo Validating bundled FSAI snapshot...
python scripts\validate_fsai_snapshot.py
if errorlevel 1 exit /b 1

echo.
echo Setup complete.
echo Start SentiOH with:
echo   streamlit run app.py

endlocal
