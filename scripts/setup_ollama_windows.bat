@echo off
setlocal

set SENTIOH_OLLAMA_MODEL=llama3.2:latest

echo ============================================
echo SentiOH local Ollama setup
echo Model: %SENTIOH_OLLAMA_MODEL%
echo ============================================

where ollama >nul 2>nul
if errorlevel 1 (
    echo.
    echo Ollama CLI was not found.
    echo Install Ollama for Windows, start the Ollama application,
    echo then run this script again.
    exit /b 1
)

echo.
echo Pulling %SENTIOH_OLLAMA_MODEL% ...
ollama pull %SENTIOH_OLLAMA_MODEL%
if errorlevel 1 exit /b 1

echo.
echo Installed Ollama models:
ollama list

echo.
echo Checking SentiOH connection...
python scripts\check_ollama.py
if errorlevel 1 exit /b 1

echo.
echo Ollama is ready.
echo Start SentiOH with:
echo   streamlit run app.py

endlocal
