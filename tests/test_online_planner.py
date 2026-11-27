import json

from agent.planner import OpenAICompatibleJSONPlanner
from agent.state import InvestigationState


class FakeResponse:
    def __init__(self, content):
        self.content = content

    def raise_for_status(self):
        return None

    def json(self):
        return {"choices": [{"message": {"content": self.content}}]}


def test_online_planner_defaults_to_groq_and_uses_groq_api_key(monkeypatch):
    monkeypatch.delenv("SENTIOH_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("SENTIOH_LLM_API_KEY", raising=False)
    monkeypatch.delenv("SENTIOH_LLM_MODEL", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "test-key")

    planner = OpenAICompatibleJSONPlanner()

    assert planner.base_url == "https://api.groq.com/openai/v1"
    assert planner.model == "openai/gpt-oss-20b"
    assert planner.api_key == "test-key"


def test_groq_planner_requires_api_key(monkeypatch):
    monkeypatch.delenv("SENTIOH_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("SENTIOH_LLM_MODEL", raising=False)
    monkeypatch.delenv("SENTIOH_LLM_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    try:
        OpenAICompatibleJSONPlanner()
    except ValueError as exc:
        assert "GROQ_API_KEY" in str(exc)
    else:
        raise AssertionError("Groq planner should require an API key.")


def test_online_planner_calls_chat_completions_with_json_mode(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    planner = OpenAICompatibleJSONPlanner()
    state = InvestigationState(recall_id="R-ONLINE")
    expected = {
        "summary": "Load recall details.",
        "action": "CALL_TOOL",
        "tool": "get_recall",
        "arguments": {"recall_id": "R-ONLINE"},
    }
    request = {}

    def fake_post(url, **kwargs):
        request["url"] = url
        request.update(kwargs)
        return FakeResponse(json.dumps(expected))

    monkeypatch.setattr("agent.planner.requests.post", fake_post)

    decision = planner.decide(state)

    assert request["url"] == "https://api.groq.com/openai/v1/chat/completions"
    assert request["headers"]["Authorization"] == "Bearer test-key"
    assert request["json"]["response_format"] == {"type": "json_object"}
    assert decision == expected


def test_online_planner_generates_recommendation(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    planner = OpenAICompatibleJSONPlanner()
    state = InvestigationState(recall_id="R-ONLINE-REC")
    state.exposure = {"status": "CONFIRMED"}
    expected = {
        "headline": "Confirmed exposure",
        "justification": "Structured evidence confirms the affected lot.",
        "recommended_next_step": "Request human approval.",
    }
    monkeypatch.setattr(
        "agent.planner.requests.post",
        lambda *args, **kwargs: FakeResponse(json.dumps(expected)),
    )

    assert planner.generate_recommendation(state) == expected
