# SentiOH agentic architecture

## Design principle

SentiOH uses **evidence-grounded bounded agency**.

The planner chooses what evidence to obtain next. Structured tools obtain company
records. A deterministic resolver determines exposure. Workflow policy creates
response tasks. Protected actions remain behind an explicit human approval gate.

```text
Recall
  |
  v
SentiOH Investigation Agent
  |
  +--> get_recall
  +--> search_catalogue
  +--> get_batches
  +--> resolve_exposure  <-- deterministic decision boundary
  +--> get_inventory
  +--> get_dispatches
  +--> get_purchase_history
  +--> open_response_case
  +--> request_human_approval
                          |
                          v
                     HUMAN REVIEW
```

The agent has no autonomous `approve`, `send`, `release`, `close case` or external
communication tool.

## Planner modes

### Offline bounded planner

The default `RulePlanner` runs without internet or an API key. It autonomously
chooses the next approved tool from investigation state and stops after a maximum
of 16 steps.

### Optional LLM planner

`OpenAICompatibleJSONPlanner` can call a configured OpenAI-compatible Chat
Completions endpoint. It is still constrained to the same tool registry and
tool-level policy boundary. Deterministic exposure resolution is unchanged.

## Why this is agentic

The platform has a persistent investigation state, a goal, a bounded
observe-decide-act loop, explicit tools, conditional investigation paths,
evidence gathering, case creation, stopping conditions and human escalation.

It is intentionally not an unrestricted autonomous agent.
