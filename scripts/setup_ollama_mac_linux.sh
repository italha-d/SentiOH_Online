#!/usr/bin/env bash
set -euo pipefail

export SENTIOH_OLLAMA_MODEL="${SENTIOH_OLLAMA_MODEL:-llama3.2:latest}"

echo "SentiOH local Ollama setup"
echo "Model: ${SENTIOH_OLLAMA_MODEL}"

if ! command -v ollama >/dev/null 2>&1; then
  echo "Ollama CLI was not found. Install and start Ollama, then rerun this script."
  exit 1
fi

ollama pull "${SENTIOH_OLLAMA_MODEL}"
ollama list
python scripts/check_ollama.py

echo "Ollama is ready."
echo "Start SentiOH with: streamlit run app.py"
