from __future__ import annotations

import os
import sys

import requests


BASE_URL = os.getenv(
    "SENTIOH_OLLAMA_BASE_URL",
    "http://localhost:11434",
).rstrip("/")
MODEL = os.getenv(
    "SENTIOH_OLLAMA_MODEL",
    "llama3.2:latest",
)


def main():
    print("SentiOH Ollama check")
    print(f"Server: {BASE_URL}")
    print(f"Model:  {MODEL}")

    try:
        response = requests.get(
            f"{BASE_URL}/api/tags",
            timeout=5,
        )
        response.raise_for_status()
    except Exception as exc:
        print("\nFAIL: Ollama is not reachable.")
        print("Start the Ollama application/service and try again.")
        print(f"Details: {exc}")
        return 2

    names = [
        item.get("name", "")
        for item in response.json().get("models", [])
    ]
    print("\nInstalled models:")
    for name in names:
        print(f"  - {name}")

    if MODEL not in names:
        print(f"\nFAIL: {MODEL} is not installed.")
        print(f"Run: ollama pull {MODEL}")
        return 3

    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "user",
                "content": "Reply with exactly: SENTIOH_OLLAMA_OK",
            }
        ],
        "stream": False,
        "think": False,
        "options": {"temperature": 0},
    }

    try:
        response = requests.post(
            f"{BASE_URL}/api/chat",
            json=payload,
            timeout=90,
        )
        response.raise_for_status()
        content = (
            (response.json().get("message") or {})
            .get("content", "")
            .strip()
        )
    except Exception as exc:
        print("\nFAIL: Model is installed but could not generate a response.")
        print(f"Details: {exc}")
        return 4

    print(f"\nModel response: {content}")
    print("PASS: Local Ollama is ready for SentiOH.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
