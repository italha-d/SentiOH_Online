from __future__ import annotations

from agent.planner import OllamaToolPlanner
from agent.state import InvestigationState


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def test_default_ollama_model_is_llama32_latest():
    planner = OllamaToolPlanner()
    assert planner.model == "llama3.2:latest"


def test_plain_text_does_not_prematurely_finish_when_recall_is_missing(monkeypatch):
    state = InvestigationState(recall_id="R-L32")
    planner = OllamaToolPlanner(model="llama3.2:latest", retries=1)

    responses = iter([
        FakeResponse({
            "message": {
                "content": "I should inspect the recall first.",
                "tool_calls": [],
            }
        }),
        FakeResponse({
            "message": {
                "content": "Loading recall evidence.",
                "tool_calls": [{
                    "function": {
                        "name": "get_recall",
                        "arguments": {"recall_id": "invented"},
                    }
                }],
            }
        }),
    ])

    monkeypatch.setattr(
        "agent.planner.requests.post",
        lambda *args, **kwargs: next(responses),
    )

    decision = planner.decide(state)
    assert decision["action"] == "CALL_TOOL"
    assert decision["tool"] == "get_recall"
    assert decision["arguments"]["recall_id"] == "R-L32"


def test_repeated_plain_text_uses_explicit_guardrail_recovery(monkeypatch):
    state = InvestigationState(recall_id="R-L32-RECOVERY")
    planner = OllamaToolPlanner(model="llama3.2:latest", retries=1)

    response = FakeResponse({
        "message": {
            "content": "I would inspect the recall.",
            "tool_calls": [],
        }
    })
    monkeypatch.setattr(
        "agent.planner.requests.post",
        lambda *args, **kwargs: response,
    )

    decision = planner.decide(state)
    assert decision["tool"] == "get_recall"
    assert decision["planner_source"] == "ollama-guardrail-recovery"
    assert decision["planner_model"] == "llama3.2:latest"


def test_get_batches_cannot_loop_on_already_investigated_candidate():
    state = InvestigationState(recall_id="R-LOOP")
    state.recall = {"recall_id": "R-LOOP"}
    state.candidates = [
        {"sku": "SKU1"},
        {"sku": "SKU2"},
    ]
    state.investigated_skus = ["SKU1"]
    state.active_sku = "SKU1"
    state.exposure = {
        "status": "NOT_AFFECTED",
        "reason_code": "LOT_MISMATCH",
    }

    planner = OllamaToolPlanner(model="llama3.2:latest")
    args = planner._canonicalise_arguments(
        "get_batches",
        {"sku": "SKU1"},
        state,
    )

    assert args == {"sku": "SKU2"}
