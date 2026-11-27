from __future__ import annotations

from agent.planner import OllamaToolPlanner
from agent.state import InvestigationState


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


def test_ollama_planner_uses_native_tool_call(monkeypatch):
    state = InvestigationState(recall_id="R-001")
    planner = OllamaToolPlanner(model="llama3.2:latest")

    def fake_post(url, json, timeout):
        assert url.endswith("/api/chat")
        assert json["tools"]
        assert json["think"] is False
        return FakeResponse({
            "message": {
                "role": "assistant",
                "content": "Load the recall evidence first.",
                "tool_calls": [
                    {
                        "function": {
                            "name": "get_recall",
                            "arguments": {"recall_id": "HALLUCINATED-ID"},
                        }
                    }
                ],
            }
        })

    monkeypatch.setattr("agent.planner.requests.post", fake_post)
    decision = planner.decide(state)

    assert decision["action"] == "CALL_TOOL"
    assert decision["tool"] == "get_recall"
    # Trusted state overrides the model's invented identifier.
    assert decision["arguments"] == {"recall_id": "R-001"}
    assert decision["planner_source"] == "ollama"
    assert decision["planner_model"] == "llama3.2:latest"


def test_ollama_planner_retries_blocked_tool_choice(monkeypatch):
    state = InvestigationState(recall_id="R-002")
    planner = OllamaToolPlanner(model="llama3.2:latest", retries=1)
    responses = iter([
        FakeResponse({
            "message": {
                "tool_calls": [
                    {
                        "function": {
                            "name": "get_inventory",
                            "arguments": {
                                "sku": "SKU999",
                                "batch_codes": ["X"],
                            },
                        }
                    }
                ]
            }
        }),
        FakeResponse({
            "message": {
                "content": "The recall must be loaded before inventory can be checked.",
                "tool_calls": [
                    {
                        "function": {
                            "name": "get_recall",
                            "arguments": {"recall_id": "R-002"},
                        }
                    }
                ],
            }
        }),
    ])

    def fake_post(url, json, timeout):
        return next(responses)

    monkeypatch.setattr("agent.planner.requests.post", fake_post)
    decision = planner.decide(state)

    assert decision["tool"] == "get_recall"
    assert decision["arguments"]["recall_id"] == "R-002"


def test_ollama_health_detects_installed_model(monkeypatch):
    planner = OllamaToolPlanner(model="llama3.2:latest")

    def fake_get(url, timeout):
        return FakeResponse({
            "models": [
                {"name": "llama3.2:latest"},
                {"name": "phi4-mini:latest"},
            ]
        })

    monkeypatch.setattr("agent.planner.requests.get", fake_get)
    health = planner.health()

    assert health["ok"] is True
    assert health["model_installed"] is True
    assert "llama3.2:latest" in health["installed_models"]


def test_ollama_structured_recommendation(monkeypatch):
    state = InvestigationState(recall_id="R-003")
    state.exposure = {
        "status": "CONFIRMED",
        "reason_code": "EXACT_PRODUCT_AND_LOT_MATCH",
        "sku": "SKU001",
        "matched_batches": ["LOT1"],
        "stock": 4,
        "dispatched": 2,
    }
    state.status = "AWAITING_HUMAN_APPROVAL"
    state.stop_reason = "HUMAN_APPROVAL_REQUIRED"
    state.case_id = "CASE-1"

    planner = OllamaToolPlanner(model="llama3.2:latest")

    def fake_post(url, json, timeout):
        assert json["format"]["type"] == "object"
        return FakeResponse({
            "message": {
                "content": (
                    '{"headline":"Confirmed exposure requires governed response",'
                    '"justification":"The exact affected lot is present in company evidence.",'
                    '"recommended_next_step":"Proceed to authenticated human review and approval."}'
                )
            }
        })

    monkeypatch.setattr("agent.planner.requests.post", fake_post)
    recommendation = planner.generate_recommendation(state)

    assert recommendation["headline"].startswith("Confirmed exposure")
    assert "human review" in recommendation["recommended_next_step"]


def test_dashboard_defaults_to_online_llm():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    source = (root / "ui" / "single_dashboard.py").read_text(encoding="utf-8")

    assert 'os.getenv("SENTIOH_PLANNER", "llm")' in source
    assert "OllamaToolPlanner" in source
    assert "Check local Ollama model" in source
    assert "Online LLM is the active agentic planner" in source
