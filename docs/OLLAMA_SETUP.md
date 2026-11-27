# SentiOH optional local Ollama agent setup

SentiOH can use a locally served Ollama model when `SENTIOH_PLANNER=ollama`.
The default deployment planner uses the online Groq-compatible API.

## Selected model

```text
llama3.2:latest
```

In Ollama, `llama3.2:latest` is the default 3B Llama 3.2 model.

Install it once:

```bash
ollama pull llama3.2:latest
```

The model is used for:

- choosing the next permitted investigation tool from the current state;
- producing a short operational justification for the selected tool;
- generating a concise evidence-grounded recommendation after investigation.

It is **not** the source of truth for exposure classification, stock totals,
dispatch totals or approval decisions.

## Windows quick start

1. Install and start Ollama.
2. From the repository root, create the Python environment:

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

3. Prepare/check the local model:

```bat
scripts\setup_ollama_windows.bat
```

4. Start SentiOH:

```bat
scripts\run_ollama_demo.bat
```

or:

```bat
streamlit run app.py
```

## macOS/Linux

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
scripts/setup_ollama_mac_linux.sh
streamlit run app.py
```

## Verify Ollama

```bash
python scripts/check_ollama.py
```

Expected final line:

```text
PASS: Local Ollama is ready for SentiOH.
```

## Default configuration

```text
SENTIOH_PLANNER=ollama
SENTIOH_OLLAMA_BASE_URL=http://localhost:11434
SENTIOH_OLLAMA_MODEL=llama3.2:latest
SENTIOH_OLLAMA_TIMEOUT=90
```

## Agent architecture

The local Llama 3.2 model receives:

- the investigation goal;
- the current structured `InvestigationState`;
- descriptions and JSON schemas for the permitted tools.

It can select:

- `get_recall`
- `search_catalogue`
- `get_batches`
- `resolve_exposure`
- `get_inventory`
- `get_dispatches`
- `get_purchase_history`
- `open_response_case`
- `request_human_approval`

SentiOH validates the requested tool and grounds sensitive arguments such as
recall ID, SKU, lot scope, exposure object and case ID to trusted state.

Small local models can occasionally return prose instead of a native tool call.
The Llama-specific planner therefore retries the model and refuses premature
completion while required evidence is still missing. If repeated tool calls
remain unusable, SentiOH uses an explicitly logged deterministic guardrail
recovery step rather than silently failing or inventing evidence.

The deterministic resolver remains responsible for:

- `CONFIRMED`
- `POSSIBLE`
- `NOT_AFFECTED`
- `INSUFFICIENT_EVIDENCE`

After investigation, Llama 3.2 can verbalise the structured result into a
dashboard recommendation. That text cannot change the classification or
approve/execute a protected action.

## Recall fixture check

The repository includes:

```bash
python scripts/check_recall_data.py
```

This verifies every bundled synthetic recall against the company sandbox and
checks the expected SKU, exposure state, reason code, stock and dispatch totals.

The bundled recalls are deliberately synthetic and are not represented as
verified FSAI notices.
