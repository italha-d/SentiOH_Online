@echo off
setlocal
set SENTIOH_PLANNER=ollama
set SENTIOH_OLLAMA_BASE_URL=http://localhost:11434
set SENTIOH_OLLAMA_MODEL=llama3.2:latest

echo Starting SentiOH with local Ollama model %SENTIOH_OLLAMA_MODEL%
streamlit run app.py
endlocal
