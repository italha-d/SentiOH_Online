from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
import uuid

def _now():
    return datetime.now(timezone.utc).isoformat()

@dataclass
class AgentEvent:
    step: int
    time: str
    event_type: str
    summary: str
    tool: str | None = None
    arguments: dict = field(default_factory=dict)
    observation: dict = field(default_factory=dict)

@dataclass
class InvestigationState:
    recall_id: str
    investigation_id: str = field(default_factory=lambda: "INV-"+uuid.uuid4().hex[:8].upper())
    goal: str = "Determine organisational recall exposure and prepare a governed response."
    status: str = "ACTIVE"
    step: int = 0
    recall: dict | None = None
    candidates: list = field(default_factory=list)
    candidate_index: int = 0
    active_sku: str | None = None
    batches: list = field(default_factory=list)
    exposure: dict | None = None
    inventory: dict | None = None
    dispatches: dict | None = None
    purchase_history: dict | None = None
    case_id: str | None = None
    case_action: str | None = None
    missing_evidence: list = field(default_factory=list)
    investigated_skus: list = field(default_factory=list)
    events: list[AgentEvent] = field(default_factory=list)
    stop_reason: str | None = None
    investigation_conclusion: str | None = None
    planner_source: str | None = None
    planner_model: str | None = None
    llm_recommendation: dict | None = None
    evidence_gap_analysis: dict | None = None
    reanalysis_context: dict | None = None
    reused_evidence: list = field(default_factory=list)
    llm_task_narratives_generated: int = 0
    llm_enrichment_complete: bool = False

    def log(self, event_type, summary, tool=None, arguments=None, observation=None):
        self.events.append(AgentEvent(
            step=self.step, time=_now(), event_type=event_type, summary=summary,
            tool=tool, arguments=arguments or {}, observation=observation or {}
        ))

    def as_dict(self):
        d = asdict(self)
        return d
