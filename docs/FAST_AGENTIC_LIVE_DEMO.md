# Fast Agentic Live Demo

The Live Demo uses the configured LLM as the full prototype, but reduces repeated planning latency by exposing five higher-level approved tools:

1. `get_recall`
2. `resolve_company_exposure`
3. `trace_internal_evidence`
4. `open_response_case`
5. `request_human_approval`

The LLM autonomously selects the next high-level tool. The two evidence tools execute the existing deterministic sub-tools internally:

- `resolve_company_exposure` -> `search_catalogue`, `get_batches`, `resolve_exposure`
- `trace_internal_evidence` -> `get_inventory`, `get_dispatches`, `get_purchase_history`

Every deterministic sub-tool result is retained in the parent tool observation and shown in the Live Demo trace. Exposure classification remains deterministic and consequential actions remain human-gated.

The Official FSAI tab continues to use the original granular tool-planning workflow.

For the Live Demo, task-narrative generation is skipped because the normal response workload is immediately replaced by the two-decision pitch workflow. The LLM still generates the evidence-backed advisory recommendation/rationale.

When using local Ollama, `SENTIOH_DEMO_PREWARM=1` preloads the model when the authorised Incident Manager opens the Live Demo. Set it to `0` to disable this behaviour.
