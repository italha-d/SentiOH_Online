from __future__ import annotations

import json
import os

import requests

from .prompts import SYSTEM_PROMPT
from tools.registry import TOOL_DESCRIPTIONS


class PlannerError(RuntimeError):
    """Raised when a planner cannot produce a safe, usable next action."""


class RulePlanner:
    """Offline bounded planner retained as a deterministic fallback/test planner."""

    name = "bounded-rule-planner"

    def decide(self, state):
        if state.recall is None:
            return {
                "summary": "Load the recall evidence before investigating company exposure.",
                "action": "CALL_TOOL",
                "tool": "get_recall",
                "arguments": {"recall_id": state.recall_id},
                "planner_source": "rule",
            }

        if not state.candidates:
            return {
                "summary": "Search the company catalogue for product candidates. Similarity is candidate retrieval only.",
                "action": "CALL_TOOL",
                "tool": "search_catalogue",
                "arguments": {"recall_id": state.recall_id, "limit": 5},
                "planner_source": "rule",
            }

        if state.active_sku is None:
            if state.candidate_index >= len(state.candidates):
                return {
                    "summary": "No remaining product candidate can establish actionable exposure.",
                    "action": "FINISH",
                    "tool": None,
                    "arguments": {},
                    "planner_source": "rule",
                }
            return {
                "summary": "Inspect the strongest remaining catalogue candidate and retrieve its structured lot evidence.",
                "action": "CALL_TOOL",
                "tool": "get_batches",
                "arguments": {
                    "sku": state.candidates[state.candidate_index]["sku"]
                },
                "planner_source": "rule",
            }

        if state.exposure is None:
            return {
                "summary": "Use the deterministic resolver because fuzzy matching cannot confirm exposure.",
                "action": "CALL_TOOL",
                "tool": "resolve_exposure",
                "arguments": {
                    "recall_id": state.recall_id,
                    "sku": state.active_sku,
                },
                "planner_source": "rule",
            }

        exposure_status = state.exposure.get("status")

        if exposure_status in {"NOT_AFFECTED", "INSUFFICIENT_EVIDENCE"}:
            if state.candidate_index + 1 < len(state.candidates):
                state.candidate_index += 1
                state.active_sku = None
                state.batches = []
                state.exposure = None
                return {
                    "summary": "The current candidate is not actionable; inspect the next plausible catalogue candidate.",
                    "action": "CALL_TOOL",
                    "tool": "get_batches",
                    "arguments": {
                        "sku": state.candidates[state.candidate_index]["sku"]
                    },
                    "planner_source": "rule",
                }
            return {
                "summary": "The available evidence does not establish organisational exposure.",
                "action": "FINISH",
                "tool": None,
                "arguments": {},
                "planner_source": "rule",
            }

        trace_batches = state.exposure.get("matched_batches") or (
            [state.exposure.get("batch")]
            if state.exposure.get("batch")
            else []
        )

        if state.inventory is None:
            return {
                "summary": "Retrieve structured inventory to quantify remaining stock for all relevant affected lots.",
                "action": "CALL_TOOL",
                "tool": "get_inventory",
                "arguments": {
                    "sku": state.active_sku,
                    "batch_codes": trace_batches,
                },
                "planner_source": "rule",
            }

        if state.dispatches is None:
            return {
                "summary": "Retrieve downstream dispatch records for all relevant affected lots.",
                "action": "CALL_TOOL",
                "tool": "get_dispatches",
                "arguments": {
                    "sku": state.active_sku,
                    "batch_codes": trace_batches,
                },
                "planner_source": "rule",
            }

        if state.purchase_history is None:
            return {
                "summary": "Retrieve upstream purchase history and supplier evidence for all relevant affected lots.",
                "action": "CALL_TOOL",
                "tool": "get_purchase_history",
                "arguments": {
                    "sku": state.active_sku,
                    "batch_codes": trace_batches,
                },
                "planner_source": "rule",
            }

        if state.case_id is None:
            return {
                "summary": "The exposure is CONFIRMED or POSSIBLE, so create a governed response case.",
                "action": "CALL_TOOL",
                "tool": "open_response_case",
                "arguments": {"exposure": state.exposure},
                "planner_source": "rule",
            }

        if exposure_status == "CONFIRMED":
            return {
                "summary": "Consequential response actions require recorded human approval. Stop at the approval boundary.",
                "action": "CALL_TOOL",
                "tool": "request_human_approval",
                "arguments": {"case_id": state.case_id},
                "planner_source": "rule",
            }

        return {
            "summary": "A POSSIBLE exposure case has been created with evidence-gathering tasks for human review.",
            "action": "FINISH",
            "tool": None,
            "arguments": {},
            "planner_source": "rule",
        }


FAST_DEMO_TOOL_DESCRIPTIONS = {
    "get_recall": TOOL_DESCRIPTIONS["get_recall"],
    "resolve_company_exposure": TOOL_DESCRIPTIONS["resolve_company_exposure"],
    "trace_internal_evidence": TOOL_DESCRIPTIONS["trace_internal_evidence"],
    "open_response_case": TOOL_DESCRIPTIONS["open_response_case"],
    "request_human_approval": TOOL_DESCRIPTIONS["request_human_approval"],
}

FAST_DEMO_OLLAMA_TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "get_recall",
            "description": FAST_DEMO_TOOL_DESCRIPTIONS["get_recall"],
            "parameters": {
                "type": "object",
                "properties": {"recall_id": {"type": "string"}},
                "required": ["recall_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "resolve_company_exposure",
            "description": FAST_DEMO_TOOL_DESCRIPTIONS["resolve_company_exposure"],
            "parameters": {
                "type": "object",
                "properties": {
                    "recall_id": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 5},
                },
                "required": ["recall_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "trace_internal_evidence",
            "description": FAST_DEMO_TOOL_DESCRIPTIONS["trace_internal_evidence"],
            "parameters": {
                "type": "object",
                "properties": {
                    "sku": {"type": "string"},
                    "batch_codes": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["sku", "batch_codes"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_response_case",
            "description": FAST_DEMO_TOOL_DESCRIPTIONS["open_response_case"],
            "parameters": {
                "type": "object",
                "properties": {"exposure": {"type": "object"}},
                "required": ["exposure"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "request_human_approval",
            "description": FAST_DEMO_TOOL_DESCRIPTIONS["request_human_approval"],
            "parameters": {
                "type": "object",
                "properties": {"case_id": {"type": "string"}},
                "required": ["case_id"],
            },
        },
    },
]

OLLAMA_TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "get_recall",
            "description": TOOL_DESCRIPTIONS["get_recall"],
            "parameters": {
                "type": "object",
                "properties": {
                    "recall_id": {"type": "string"},
                },
                "required": ["recall_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_catalogue",
            "description": TOOL_DESCRIPTIONS["search_catalogue"],
            "parameters": {
                "type": "object",
                "properties": {
                    "recall_id": {"type": "string"},
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 5,
                    },
                },
                "required": ["recall_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_batches",
            "description": TOOL_DESCRIPTIONS["get_batches"],
            "parameters": {
                "type": "object",
                "properties": {
                    "sku": {"type": "string"},
                },
                "required": ["sku"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "resolve_exposure",
            "description": TOOL_DESCRIPTIONS["resolve_exposure"],
            "parameters": {
                "type": "object",
                "properties": {
                    "recall_id": {"type": "string"},
                    "sku": {"type": "string"},
                },
                "required": ["recall_id", "sku"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_inventory",
            "description": TOOL_DESCRIPTIONS["get_inventory"],
            "parameters": {
                "type": "object",
                "properties": {
                    "sku": {"type": "string"},
                    "batch_codes": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": ["sku", "batch_codes"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_dispatches",
            "description": TOOL_DESCRIPTIONS["get_dispatches"],
            "parameters": {
                "type": "object",
                "properties": {
                    "sku": {"type": "string"},
                    "batch_codes": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": ["sku", "batch_codes"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_purchase_history",
            "description": TOOL_DESCRIPTIONS["get_purchase_history"],
            "parameters": {
                "type": "object",
                "properties": {
                    "sku": {"type": "string"},
                    "batch_codes": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": ["sku", "batch_codes"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_response_case",
            "description": TOOL_DESCRIPTIONS["open_response_case"],
            "parameters": {
                "type": "object",
                "properties": {
                    "exposure": {"type": "object"},
                },
                "required": ["exposure"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "request_human_approval",
            "description": TOOL_DESCRIPTIONS["request_human_approval"],
            "parameters": {
                "type": "object",
                "properties": {
                    "case_id": {"type": "string"},
                },
                "required": ["case_id"],
            },
        },
    },
]


RECOMMENDATION_SCHEMA = {
    "type": "object",
    "properties": {
        "headline": {"type": "string"},
        "justification": {"type": "string"},
        "recommended_next_step": {"type": "string"},
    },
    "required": [
        "headline",
        "justification",
        "recommended_next_step",
    ],
}


TASK_NARRATIVE_SCHEMA = {
    "type": "object",
    "properties": {
        "tasks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string"},
                    "why_generated": {"type": "string"},
                    "suggested_steps": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": [
                    "task_id",
                    "why_generated",
                    "suggested_steps",
                ],
            },
        }
    },
    "required": ["tasks"],
}


EVIDENCE_GAP_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "decisive_missing_evidence": {
            "type": "array",
            "items": {"type": "string"},
        },
        "priority_evidence": {"type": "string"},
        "why_this_evidence_first": {"type": "string"},
        "recommended_evidence_action": {"type": "string"},
        "confidence_note": {"type": "string"},
    },
    "required": [
        "summary",
        "decisive_missing_evidence",
        "priority_evidence",
        "why_this_evidence_first",
        "recommended_evidence_action",
        "confidence_note",
    ],
}


class OllamaToolPlanner:
    """
    Local LLM planner using Ollama's native function/tool-calling API.

    Default:
      base URL: http://localhost:11434
      model:    llama3.2:latest

    Environment variables:
      SENTIOH_OLLAMA_BASE_URL
      SENTIOH_OLLAMA_MODEL
      SENTIOH_OLLAMA_TIMEOUT
    """

    name = "ollama-native-tool-planner"

    def __init__(
        self,
        base_url=None,
        model=None,
        timeout=None,
        retries=2,
        fast_mode=False,
    ):
        self.base_url = (
            base_url
            or os.getenv(
                "SENTIOH_OLLAMA_BASE_URL",
                "http://localhost:11434",
            )
        ).rstrip("/")
        self.model = (
            model
            or os.getenv(
                "SENTIOH_OLLAMA_MODEL",
                "llama3.2:latest",
            )
        )
        self.timeout = float(
            timeout
            or os.getenv(
                "SENTIOH_OLLAMA_TIMEOUT",
                "90",
            )
        )
        self.retries = int(retries)
        self.fast_mode = bool(fast_mode)
        self.last_decision_source = None

    @property
    def display_name(self):
        return f"Ollama · {self.model}"

    def health(self):
        """Check whether Ollama is reachable and the configured model is installed."""
        try:
            response = requests.get(
                f"{self.base_url}/api/tags",
                timeout=3,
            )
            response.raise_for_status()
            payload = response.json()
            installed = [
                item.get("name", "")
                for item in payload.get("models", [])
            ]
            configured = self.model
            present = any(
                name == configured
                or name.split(":")[0] == configured
                for name in installed
            )
            return {
                "ok": True,
                "server": self.base_url,
                "model": configured,
                "model_installed": present,
                "installed_models": installed,
            }
        except Exception as exc:
            return {
                "ok": False,
                "server": self.base_url,
                "model": self.model,
                "model_installed": False,
                "error": str(exc),
            }

    def warmup(self):
        """Load the configured local model into Ollama memory without generation."""
        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": "",
                    "stream": False,
                    "keep_alive": "10m",
                    "options": {"num_predict": 1},
                },
                timeout=min(self.timeout, 15),
            )
            response.raise_for_status()
            return True
        except Exception:
            return False

    def _compact_state(self, state):
        if self.fast_mode:
            exposure = state.exposure or {}
            recall = state.recall or {}
            return {
                "goal": state.goal,
                "recall_id": state.recall_id,
                "status": state.status,
                "recall_loaded": state.recall is not None,
                "recall": {
                    "product_name": recall.get("product_name"),
                    "brand": recall.get("brand"),
                    "batch_codes": recall.get("batch_codes") or [],
                    "use_by": recall.get("use_by") or [],
                    "best_before": recall.get("best_before") or [],
                } if state.recall else None,
                "active_sku": state.active_sku,
                "exposure": {
                    "status": exposure.get("status"),
                    "reason_code": exposure.get("reason_code"),
                    "sku": exposure.get("sku"),
                    "matched_batches": exposure.get("matched_batches") or [],
                } if state.exposure else None,
                "internal_evidence_collected": bool(
                    state.inventory is not None
                    and state.dispatches is not None
                    and state.purchase_history is not None
                ),
                "case_id": state.case_id,
            }
        return {
            "goal": state.goal,
            "recall_id": state.recall_id,
            "status": state.status,
            "recall": state.recall,
            "candidates": state.candidates,
            "candidate_index": state.candidate_index,
            "active_sku": state.active_sku,
            "batches": state.batches,
            "exposure": state.exposure,
            "inventory": state.inventory,
            "dispatches": state.dispatches,
            "purchase_history": state.purchase_history,
            "case_id": state.case_id,
            "missing_evidence": state.missing_evidence,
            "investigated_skus": state.investigated_skus,
            "reanalysis_context": state.reanalysis_context,
            "reused_evidence": state.reused_evidence,
            "evidence_gap_analysis": state.evidence_gap_analysis,
        }

    def _trace_batches(self, state):
        if not state.exposure:
            return []
        return state.exposure.get("matched_batches") or (
            [state.exposure.get("batch")]
            if state.exposure.get("batch")
            else []
        )

    def _candidate_skus(self, state):
        return [
            item.get("sku")
            for item in state.candidates
            if item.get("sku")
        ]

    def _uninvestigated_skus(self, state):
        done = set(state.investigated_skus or [])
        return [
            sku
            for sku in self._candidate_skus(state)
            if sku not in done
        ]

    def _can_finish(self, state):
        """
        Plain-text FINISH responses from small local models are accepted only
        when the structured investigation state genuinely supports stopping.
        """
        if state.recall is None:
            return False

        if not state.candidates:
            return any(
                event.tool == "search_catalogue"
                for event in state.events
            )

        exposure_status = (
            state.exposure.get("status")
            if state.exposure
            else None
        )

        if exposure_status == "POSSIBLE":
            return bool(state.case_id)

        if exposure_status == "CONFIRMED":
            # A confirmed case must reach the explicit human-approval tool.
            return False

        if exposure_status in {
            "NOT_AFFECTED",
            "INSUFFICIENT_EVIDENCE",
        }:
            return not self._uninvestigated_skus(state)

        return False

    def _safe_recovery_decision(self, state, reason):
        """
        Deterministic safety recovery used only after the local LLM repeatedly
        fails to emit a usable tool call. It keeps the demo running while the
        event metadata makes the fallback explicit.
        """
        if self.fast_mode:
            exposure_status = (state.exposure or {}).get("status")
            if state.recall is None:
                decision = {"action": "CALL_TOOL", "tool": "get_recall", "arguments": {"recall_id": state.recall_id}, "summary": "Load verified recall evidence."}
            elif state.exposure is None:
                decision = {"action": "CALL_TOOL", "tool": "resolve_company_exposure", "arguments": {"recall_id": state.recall_id, "limit": 5}, "summary": "Resolve the recall against company product and lot evidence."}
            elif exposure_status in {"CONFIRMED", "POSSIBLE"} and (state.inventory is None or state.dispatches is None or state.purchase_history is None):
                decision = {"action": "CALL_TOOL", "tool": "trace_internal_evidence", "arguments": {"sku": state.active_sku, "batch_codes": self._trace_batches(state)}, "summary": "Trace stock, dispatch and purchase evidence."}
            elif exposure_status in {"CONFIRMED", "POSSIBLE"} and state.case_id is None:
                decision = {"action": "CALL_TOOL", "tool": "open_response_case", "arguments": {"exposure": state.exposure}, "summary": "Open the governed response case."}
            elif exposure_status == "CONFIRMED" and state.case_id:
                decision = {"action": "CALL_TOOL", "tool": "request_human_approval", "arguments": {"case_id": state.case_id}, "summary": "Stop at the human approval boundary."}
            else:
                decision = {"action": "FINISH", "tool": None, "arguments": {}, "summary": "The investigation can safely finish."}
        else:
            decision = RulePlanner().decide(state)
        decision["planner_source"] = "ollama-guardrail-recovery"
        decision["planner_model"] = self.model
        decision["summary"] = (
            f"Local Llama 3.2 planner needed guardrail recovery: {reason} "
            + decision.get("summary", "")
        ).strip()
        return decision

    def _canonicalise_arguments(self, tool, arguments, state):
        """
        The LLM chooses the tool; deterministic code binds sensitive identifiers
        to previously observed state so the model cannot invent a recall, SKU,
        lot scope, exposure object or case identifier.
        """
        arguments = arguments or {}

        if tool == "get_recall":
            return {"recall_id": state.recall_id}

        if tool == "search_catalogue":
            limit = arguments.get("limit", 5)
            try:
                limit = int(limit)
            except (TypeError, ValueError):
                limit = 5
            return {
                "recall_id": state.recall_id,
                "limit": min(max(limit, 1), 5),
            }

        if tool == "get_batches":
            uninvestigated = self._uninvestigated_skus(state)

            # The LLM chooses the investigation tool. Catalogue ranking remains
            # deterministic, so candidate traversal always follows the strongest
            # still-uninvestigated product returned by search_catalogue.
            # This prevents a small local model from skipping to a weaker fuzzy
            # candidate or repeatedly revisiting the same SKU.
            requested = (
                uninvestigated[0]
                if uninvestigated
                else None
            )
            return {"sku": requested}

        if tool == "resolve_exposure":
            return {
                "recall_id": state.recall_id,
                "sku": state.active_sku,
            }

        if tool in {
            "get_inventory",
            "get_dispatches",
            "get_purchase_history",
        }:
            return {
                "sku": state.active_sku,
                "batch_codes": self._trace_batches(state),
            }

        if tool == "resolve_company_exposure":
            limit = arguments.get("limit", 5)
            try:
                limit = int(limit)
            except (TypeError, ValueError):
                limit = 5
            return {
                "recall_id": state.recall_id,
                "limit": min(max(limit, 1), 5),
            }

        if tool == "trace_internal_evidence":
            return {
                "sku": state.active_sku,
                "batch_codes": self._trace_batches(state),
            }

        if tool == "open_response_case":
            return {"exposure": state.exposure}

        if tool == "request_human_approval":
            return {"case_id": state.case_id}

        return arguments

    def _tool_allowed_now(self, tool, state):
        """State-aware guardrail around the LLM's tool choice."""
        exposure_status = (
            state.exposure.get("status")
            if state.exposure
            else None
        )

        if tool == "resolve_company_exposure":
            return state.recall is not None and state.exposure is None

        if tool == "trace_internal_evidence":
            return (
                exposure_status in {"CONFIRMED", "POSSIBLE"}
                and bool(state.active_sku)
                and (
                    state.inventory is None
                    or state.dispatches is None
                    or state.purchase_history is None
                )
            )

        if tool == "get_recall":
            return state.recall is None

        if tool == "search_catalogue":
            return state.recall is not None and not state.candidates

        if tool == "get_batches":
            exposure_status = (
                state.exposure.get("status")
                if state.exposure
                else None
            )
            may_switch_candidate = (
                state.active_sku is None
                or exposure_status in {
                    "NOT_AFFECTED",
                    "INSUFFICIENT_EVIDENCE",
                }
            )
            return (
                bool(self._uninvestigated_skus(state))
                and may_switch_candidate
            )

        if tool == "resolve_exposure":
            return bool(state.active_sku) and state.exposure is None

        if tool == "get_inventory":
            return (
                exposure_status in {"CONFIRMED", "POSSIBLE"}
                and state.inventory is None
            )

        if tool == "get_dispatches":
            return (
                exposure_status in {"CONFIRMED", "POSSIBLE"}
                and state.dispatches is None
            )

        if tool == "get_purchase_history":
            return (
                exposure_status in {"CONFIRMED", "POSSIBLE"}
                and state.purchase_history is None
            )

        if tool == "open_response_case":
            return (
                exposure_status in {"CONFIRMED", "POSSIBLE"}
                and state.case_id is None
            )

        if tool == "request_human_approval":
            return (
                exposure_status == "CONFIRMED"
                and bool(state.case_id)
            )

        return False

    def _planner_prompt(self, state, correction=None):
        prompt = {
            "instruction": (
                (
                    "You are the active agentic tool-selection planner for a fast live demo. "
                    "Select exactly ONE high-level approved tool whenever more work is required. "
                    "The high-level tools execute deterministic sub-tools internally and preserve "
                    "their evidence trace. Do not invent identifiers or determine exposure yourself. "
                    "Only finish when the structured state proves the investigation can safely stop."
                )
                if self.fast_mode
                else (
                    "You are the active tool-selection planner. Select exactly ONE tool call "
                    "whenever further evidence or workflow work is required. Do not answer with "
                    "plain prose while a valid next tool remains. Use the current state only. "
                    "Do not invent identifiers. Do not determine exposure yourself; call "
                    "resolve_exposure. Only finish without a tool when the structured state "
                    "already proves the investigation can safely stop."
                )
            ),
            "current_investigation_state": self._compact_state(state),
            "available_tool_descriptions": (
                FAST_DEMO_TOOL_DESCRIPTIONS if self.fast_mode else TOOL_DESCRIPTIONS
            ),
        }
        if correction:
            prompt["previous_call_was_blocked"] = correction
        return json.dumps(prompt, default=str)

    def decide(self, state):
        correction = None
        last_error = None

        for _ in range(self.retries + 1):
            payload = {
                "model": self.model,
                "messages": [
                    {
                        "role": "system",
                        "content": SYSTEM_PROMPT,
                    },
                    {
                        "role": "user",
                        "content": self._planner_prompt(
                            state,
                            correction=correction,
                        ),
                    },
                ],
                "tools": (FAST_DEMO_OLLAMA_TOOL_SCHEMAS if self.fast_mode else OLLAMA_TOOL_SCHEMAS),
                "stream": False,
                "think": False,
                "options": ({"temperature": 0, "num_predict": 72} if self.fast_mode else {"temperature": 0}),
                "keep_alive": "10m",
            }

            try:
                response = requests.post(
                    f"{self.base_url}/api/chat",
                    json=payload,
                    timeout=self.timeout,
                )
                response.raise_for_status()
                body = response.json()
            except Exception as exc:
                raise PlannerError(
                    "Local Ollama planner is unavailable. "
                    f"Server={self.base_url}, model={self.model}. "
                    "Start Ollama and ensure the model is installed. "
                    f"Underlying error: {exc}"
                ) from exc

            message = body.get("message") or {}
            tool_calls = message.get("tool_calls") or []
            content = (message.get("content") or "").strip()

            if not tool_calls:
                if self._can_finish(state):
                    self.last_decision_source = "ollama"
                    return {
                        "summary": (
                            content
                            or "The local LLM determined that the investigation can safely finish."
                        ),
                        "action": "FINISH",
                        "tool": None,
                        "arguments": {},
                        "planner_source": "ollama",
                        "planner_model": self.model,
                    }

                last_error = (
                    "The model returned plain text even though the structured "
                    "state still requires another tool call."
                )
                correction = (
                    last_error
                    + " You MUST emit exactly one native tool call now."
                )
                continue

            call = tool_calls[0]
            function = call.get("function") or {}
            tool = function.get("name")
            arguments = function.get("arguments") or {}

            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except json.JSONDecodeError:
                    arguments = {}

            if not self._tool_allowed_now(tool, state):
                last_error = (
                    f"Tool '{tool}' is not valid for the current investigation state."
                )
                correction = (
                    last_error
                    + " Re-evaluate the observed state and choose a different permitted tool."
                )
                continue

            grounded_arguments = self._canonicalise_arguments(
                tool,
                arguments,
                state,
            )

            if any(
                value is None
                for value in grounded_arguments.values()
            ):
                last_error = (
                    f"Tool '{tool}' lacks a grounded identifier in the current state."
                )
                correction = (
                    last_error
                    + " Choose a tool whose required evidence is already available."
                )
                continue

            self.last_decision_source = "ollama"
            return {
                "summary": (
                    content
                    or f"Local LLM selected {tool} as the next evidence-gathering action."
                ),
                "action": "CALL_TOOL",
                "tool": tool,
                "arguments": grounded_arguments,
                "planner_source": "ollama",
                "planner_model": self.model,
            }

        self.last_decision_source = "ollama-guardrail-recovery"
        return self._safe_recovery_decision(
            state,
            last_error or "no usable native tool call was returned",
        )


    def _structured_chat(self, system, prompt, schema):
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "stream": False,
            "think": False,
            "format": schema,
            "options": {"temperature": 0},
            "keep_alive": "10m",
        }

        response = requests.post(
            f"{self.base_url}/api/chat",
            json=payload,
            timeout=self.timeout,
        )
        response.raise_for_status()
        content = (
            (response.json().get("message") or {})
            .get("content", "")
            .strip()
        )
        return json.loads(content)

    def analyse_evidence_gap(self, state):
        """
        Explain what evidence is missing for a POSSIBLE exposure.
        The analysis can prioritise evidence gathering, but it cannot alter the
        deterministic exposure state or authorise a protected action.
        """
        if not state.exposure or state.exposure.get("status") != "POSSIBLE":
            return None

        evidence = {
            "recall_id": state.recall_id,
            "sku": state.exposure.get("sku"),
            "reason_code": state.exposure.get("reason_code"),
            "missing_evidence": state.missing_evidence,
            "matched_batches": state.exposure.get("matched_batches") or [],
            "batch_match": state.exposure.get("batch_match"),
            "date_match": state.exposure.get("date_match"),
            "product_name_similarity": state.exposure.get("product_name_similarity"),
            "brand_match": state.exposure.get("brand_match"),
            "pack_size_match": state.exposure.get("pack_size_match"),
            "remaining_stock": (
                (state.inventory or {}).get(
                    "total_quantity",
                    state.exposure.get("stock", 0),
                )
            ),
            "dispatched": (
                (state.dispatches or {}).get(
                    "total_dispatched",
                    state.exposure.get("dispatched", 0),
                )
            ),
        }

        prompt = (
            "Analyse the unresolved evidence in this POSSIBLE recall exposure. "
            "Use only the structured evidence supplied. Identify the decisive "
            "missing evidence and recommend the safest internal evidence-gathering "
            "action to perform first. Do not recommend customer/supplier contact, "
            "stock release, case closure or any protected external/consequential "
            "action. Do not change the exposure classification.\n\nEvidence:\n"
            + json.dumps(evidence, default=str)
        )

        return self._structured_chat(
            (
                "You are SentiOH's local evidence-gap analyst. "
                "Your role is to prioritise evidence collection, not make the "
                "deterministic recall decision."
            ),
            prompt,
            EVIDENCE_GAP_SCHEMA,
        )

    def generate_task_narratives(self, state, tasks):
        """
        Generate case-specific rationale and suggested steps for existing
        deterministic tasks. Governance fields are deliberately excluded from
        the model's output schema and cannot be changed by this method.
        """
        if not tasks or not state.exposure:
            return []

        task_inputs = []
        for task in tasks:
            task_inputs.append({
                "task_id": task.get("task_id"),
                "title": task.get("title"),
                "description": task.get("description"),
                "priority": task.get("priority"),
                "assigned_to": task.get("assigned_to"),
                "requires_approval": task.get("requires_approval"),
                "approval_roles": task.get("approval_roles") or [],
                "approval_mode": task.get("approval_mode"),
                "evidence": task.get("evidence") or {},
                "completion_evidence": task.get("completion_evidence") or [],
                "completion_criteria": task.get("completion_criteria"),
                "action_boundary": task.get("action_boundary"),
            })

        context = {
            "recall_id": state.recall_id,
            "exposure": state.exposure,
            "inventory_total": (
                (state.inventory or {}).get("total_quantity")
            ),
            "dispatch_total": (
                (state.dispatches or {}).get("total_dispatched")
            ),
            "missing_evidence": state.missing_evidence,
            "evidence_gap_analysis": state.evidence_gap_analysis,
            "reanalysis_context": state.reanalysis_context,
            "tasks": task_inputs,
        }

        prompt = (
            "For each existing SentiOH task, generate a concise case-specific "
            "'why this task was created' explanation and 2-5 suggested operator "
            "steps. Use only the supplied structured evidence. Never invent an "
            "identifier, quantity, regulator instruction, approval, completed "
            "action or communication. Do not change the task title, assignment, "
            "priority, approval authority, completion evidence, completion "
            "criterion or agent boundary. If a task requires approval, the steps "
            "must preserve that approval before any protected action occurs. "
            "Return one entry for every supplied task_id.\n\nContext:\n"
            + json.dumps(context, default=str)
        )

        result = self._structured_chat(
            (
                "You are SentiOH's local operational explanation generator. "
                "You verbalise deterministic case evidence but never change "
                "governance or the underlying decision."
            ),
            prompt,
            TASK_NARRATIVE_SCHEMA,
        )
        return result.get("tasks") or []
    def generate_recommendation(self, state):
        """
        Convert the already-established structured evidence into a concise,
        human-readable recommendation. This text is advisory only: it does not
        alter exposure status, create approval decisions or execute actions.
        """
        evidence = {
            "recall_id": state.recall_id,
            "exposure_status": (
                state.exposure.get("status")
                if state.exposure
                else None
            ),
            "reason_code": (
                state.exposure.get("reason_code")
                if state.exposure
                else None
            ),
            "sku": (
                state.exposure.get("sku")
                if state.exposure
                else None
            ),
            "matched_batches": (
                state.exposure.get("matched_batches") or []
                if state.exposure
                else []
            ),
            "remaining_stock": (
                (state.inventory or {}).get(
                    "total_quantity",
                    (state.exposure or {}).get("stock", 0),
                )
            ),
            "dispatched": (
                (state.dispatches or {}).get(
                    "total_dispatched",
                    (state.exposure or {}).get("dispatched", 0),
                )
            ),
            "missing_evidence": state.missing_evidence,
            "case_id": state.case_id,
            "agent_status": state.status,
            "stop_reason": state.stop_reason,
            "evidence_gap_analysis": state.evidence_gap_analysis,
            "reanalysis_context": state.reanalysis_context,
            "reused_evidence": state.reused_evidence,
        }

        prompt = (
            "You are generating an operational recommendation for SentiOH. "
            "Use ONLY the supplied structured evidence. Do not invent facts, "
            "do not change the exposure classification, and do not claim that "
            "a protected action has been approved or executed. If human approval "
            "is required, explicitly say so. Produce concise language suitable "
            "for a food-safety incident dashboard.\n\nEvidence:\n"
            + json.dumps(evidence, default=str)
        )

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Convert structured evidence into a concise operational "
                        "explanation. The deterministic evidence engine remains "
                        "the source of truth."
                    ),
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            "stream": False,
            "think": False,
            "format": RECOMMENDATION_SCHEMA,
            "options": ({"temperature": 0, "num_predict": 180} if self.fast_mode else {"temperature": 0}),
            "keep_alive": "10m",
        }

        try:
            response = requests.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()
            content = (
                (response.json().get("message") or {})
                .get("content", "")
                .strip()
            )
            recommendation = json.loads(content)
        except Exception as exc:
            raise PlannerError(
                "The local Ollama planner completed the investigation, but "
                f"recommendation text generation failed: {exc}"
            ) from exc

        return recommendation


class OpenAICompatibleJSONPlanner:
    """
    Planner for an OpenAI-compatible Chat Completions endpoint.

    Defaults to Groq; endpoint, model, and API key can be overridden with
    SENTIOH_LLM_BASE_URL, SENTIOH_LLM_MODEL, and SENTIOH_LLM_API_KEY.
    """

    name = "openai-compatible-json-planner"

    def __init__(
        self,
        base_url=None,
        api_key=None,
        model=None,
        timeout=45,
    ):
        self.base_url = (
            base_url
            or os.getenv("SENTIOH_LLM_BASE_URL")
            or "https://api.groq.com/openai/v1"
        ).rstrip("/")
        self.api_key = (
            api_key
            if api_key is not None
            else os.getenv("SENTIOH_LLM_API_KEY")
            or os.getenv("GROQ_API_KEY", "")
        )
        self.model = (
            model
            or os.getenv("SENTIOH_LLM_MODEL", "")
            or "openai/gpt-oss-20b"
        )
        self.timeout = timeout
        if not self.base_url or not self.model:
            raise ValueError(
                "SENTIOH_LLM_BASE_URL and SENTIOH_LLM_MODEL are required."
            )
        if "api.groq.com" in self.base_url and not self.api_key:
            raise ValueError(
                "GROQ_API_KEY or SENTIOH_LLM_API_KEY is required for the Groq planner."
            )

    @property
    def display_name(self):
        provider = "Groq" if "api.groq.com" in self.base_url else "Online LLM"
        return f"{provider} · {self.model}"

    def _chat_json(self, system, prompt, schema=None):
        if schema:
            system = (
                f"{system}\nReturn a JSON object matching this schema:\n"
                f"{json.dumps(schema)}"
            )
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        response = requests.post(
            f"{self.base_url}/chat/completions",
            headers=headers,
            json={
                "model": self.model,
                "temperature": 0,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"].strip()
        if content.startswith("```"):
            content = content.strip("`")
            if content.lower().startswith("json"):
                content = content[4:].strip()
        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            raise PlannerError(
                "The online LLM returned a response that was not valid JSON."
            ) from exc

    def decide(self, state):
        compact_state = {
            "recall_id": state.recall_id,
            "status": state.status,
            "recall": state.recall,
            "candidates": state.candidates,
            "candidate_index": state.candidate_index,
            "active_sku": state.active_sku,
            "batches": state.batches,
            "exposure": state.exposure,
            "inventory": state.inventory,
            "dispatches": state.dispatches,
            "purchase_history": state.purchase_history,
            "case_id": state.case_id,
            "missing_evidence": state.missing_evidence,
        }
        user = {
            "available_tools": TOOL_DESCRIPTIONS,
            "investigation_state": compact_state,
        }
        return self._chat_json(
            SYSTEM_PROMPT,
            json.dumps(user),
        )

    def analyse_evidence_gap(self, state):
        if not state.exposure or state.exposure.get("status") != "POSSIBLE":
            return None

        evidence = {
            "recall_id": state.recall_id,
            "sku": state.exposure.get("sku"),
            "reason_code": state.exposure.get("reason_code"),
            "missing_evidence": state.missing_evidence,
            "matched_batches": state.exposure.get("matched_batches") or [],
            "batch_match": state.exposure.get("batch_match"),
            "date_match": state.exposure.get("date_match"),
            "brand_match": state.exposure.get("brand_match"),
            "pack_size_match": state.exposure.get("pack_size_match"),
            "remaining_stock": (state.inventory or {}).get(
                "total_quantity", state.exposure.get("stock", 0)
            ),
            "dispatched": (state.dispatches or {}).get(
                "total_dispatched", state.exposure.get("dispatched", 0)
            ),
        }
        return self._chat_json(
            (
                "You are SentiOH's evidence-gap analyst. Prioritise evidence "
                "collection without changing deterministic exposure status or "
                "recommending protected actions."
            ),
            (
                "Using only this structured evidence, identify decisive missing "
                "evidence and the safest internal evidence-gathering action. Do "
                "not recommend customer/supplier contact, stock release, case "
                "closure, or other protected actions.\n\nEvidence:\n"
                + json.dumps(evidence, default=str)
            ),
            EVIDENCE_GAP_SCHEMA,
        )

    def generate_task_narratives(self, state, tasks):
        if not tasks or not state.exposure:
            return []

        context = {
            "recall_id": state.recall_id,
            "exposure": state.exposure,
            "inventory_total": (state.inventory or {}).get("total_quantity"),
            "dispatch_total": (state.dispatches or {}).get("total_dispatched"),
            "missing_evidence": state.missing_evidence,
            "evidence_gap_analysis": state.evidence_gap_analysis,
            "reanalysis_context": state.reanalysis_context,
            "tasks": [
                {
                    "task_id": task.get("task_id"),
                    "title": task.get("title"),
                    "description": task.get("description"),
                    "priority": task.get("priority"),
                    "assigned_to": task.get("assigned_to"),
                    "approval_roles": task.get("approval_roles") or [],
                    "approval_mode": task.get("approval_mode"),
                    "evidence": task.get("evidence") or {},
                    "completion_evidence": task.get("completion_evidence") or [],
                    "completion_criteria": task.get("completion_criteria"),
                    "action_boundary": task.get("action_boundary"),
                }
                for task in tasks
            ],
        }
        result = self._chat_json(
            (
                "You are SentiOH's operational explanation generator. "
                "Describe supplied evidence without changing governance or "
                "the underlying decision."
            ),
            (
                "For each supplied task, provide concise case-specific rationale "
                "and 2-5 suggested operator steps. Do not invent identifiers, "
                "quantities, approvals, completed actions, or communications. "
                "Preserve approval requirements and return an entry for each "
                "task_id.\n\nContext:\n" + json.dumps(context, default=str)
            ),
            TASK_NARRATIVE_SCHEMA,
        )
        return result.get("tasks") or []

    def generate_recommendation(self, state):
        evidence = {
            "recall_id": state.recall_id,
            "exposure_status": (
                state.exposure.get("status") if state.exposure else None
            ),
            "reason_code": (
                state.exposure.get("reason_code") if state.exposure else None
            ),
            "sku": state.exposure.get("sku") if state.exposure else None,
            "matched_batches": (
                state.exposure.get("matched_batches") or []
                if state.exposure
                else []
            ),
            "remaining_stock": (state.inventory or {}).get(
                "total_quantity", (state.exposure or {}).get("stock", 0)
            ),
            "dispatched": (state.dispatches or {}).get(
                "total_dispatched", (state.exposure or {}).get("dispatched", 0)
            ),
            "missing_evidence": state.missing_evidence,
            "case_id": state.case_id,
            "agent_status": state.status,
            "stop_reason": state.stop_reason,
            "evidence_gap_analysis": state.evidence_gap_analysis,
            "reanalysis_context": state.reanalysis_context,
            "reused_evidence": state.reused_evidence,
        }
        return self._chat_json(
            (
                "Convert structured recall evidence into a concise operational "
                "recommendation. Deterministic evidence is the source of truth."
            ),
            (
                "Use only the supplied evidence. Do not invent facts, alter "
                "exposure classification, or claim a protected action has been "
                "approved or executed. Explicitly state when human approval is "
                "required.\n\nEvidence:\n" + json.dumps(evidence, default=str)
            ),
            RECOMMENDATION_SCHEMA,
        )
