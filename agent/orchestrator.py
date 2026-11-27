from __future__ import annotations

from .state import InvestigationState
from .policies import MAX_AGENT_STEPS, validate_tool_call
from tools.registry import execute_tool
from workflow.llm_enrichment import (
    apply_task_narratives,
    store_evidence_gap_analysis,
)
from workflow.audit import add_event, now_iso


IDENTITY_FIELDS = {
    "product_name",
    "brand",
    "pack_sizes",
    "gtins",
    "barcodes",
}


class SentiOHAgent:
    def __init__(
        self,
        tool_context,
        planner,
        max_steps=MAX_AGENT_STEPS,
        enrichment_mode="full",
    ):
        self.ctx = tool_context
        self.planner = planner
        self.max_steps = max_steps
        self.enrichment_mode = enrichment_mode

    def _existing_case_for_recall(self, recall_id):
        return next(
            (
                case
                for case in self.ctx.cases.values()
                if case.get("recall_id") == recall_id
            ),
            None,
        )

    def _initial_state(self, recall_id):
        state = InvestigationState(recall_id=recall_id)
        case = self._existing_case_for_recall(recall_id)

        if not case or not case.get("needs_reanalysis"):
            return state

        change = case.get("recall_change_summary") or {}
        changed_fields = list(change.get("changed_fields") or [])
        previous_exposure = case.get("exposure") or {}
        previous_sku = previous_exposure.get("sku")

        identity_changed = bool(
            IDENTITY_FIELDS.intersection(changed_fields)
        )
        can_reuse_product_identity = bool(
            previous_sku
            and changed_fields
            and not identity_changed
        )

        state.reanalysis_context = {
            "mode": (
                "DIFFERENTIAL"
                if can_reuse_product_identity
                else "FULL_REANALYSIS"
            ),
            "existing_case_id": case.get("case_id"),
            "previous_analysis_revision": case.get(
                "analysis_revision",
                1,
            ),
            "changed_fields": changed_fields,
            "before": change.get("before") or {},
            "after": change.get("after") or {},
            "reused_product_identity": can_reuse_product_identity,
            "reused_sku": (
                previous_sku
                if can_reuse_product_identity
                else None
            ),
            "reason": (
                "Product identity fields are unchanged, so the previous "
                "catalogue identity can be reused while changed lot/date "
                "and operational evidence is refreshed."
                if can_reuse_product_identity
                else
                "Product identity changed or cannot be safely reused, so "
                "catalogue identity will be investigated again."
            ),
        }

        if can_reuse_product_identity:
            # This deliberately skips repeated fuzzy catalogue search while
            # still forcing fresh batch, deterministic exposure, inventory,
            # dispatch and purchase-history checks.
            state.candidates = [
                {
                    "sku": previous_sku,
                    "candidate_basis": (
                        "reused_previous_case_product_identity"
                    ),
                    "reused_from_case": case.get("case_id"),
                }
            ]
            state.reused_evidence = [
                "product_identity",
                "catalogue_candidate",
            ]

        state.log(
            "REANALYSIS_CONTEXT",
            (
                "Differential recall re-analysis prepared."
                if can_reuse_product_identity
                else "Full recall re-analysis prepared."
            ),
            observation=state.reanalysis_context,
        )
        return state

    def _apply_observation(self, state, tool, obs):
        if not obs.get("ok", False):
            state.status = "ERROR"
            state.stop_reason = obs.get("error", "TOOL_ERROR")
            return

        if tool == "get_recall":
            state.recall = obs["recall"]

        elif tool == "search_catalogue":
            state.candidates = obs.get("candidates", [])
            if not state.candidates:
                state.missing_evidence = [
                    "No plausible catalogue candidate found"
                ]

        elif tool == "get_batches":
            new_sku = obs["sku"]

            if state.active_sku and new_sku != state.active_sku:
                state.exposure = None
                state.inventory = None
                state.dispatches = None
                state.purchase_history = None
                state.case_id = None
                state.case_action = None
                state.missing_evidence = []

            state.active_sku = new_sku
            state.batches = obs.get("batches", [])

            for index, candidate in enumerate(state.candidates):
                if candidate.get("sku") == new_sku:
                    state.candidate_index = index
                    break

        elif tool == "resolve_exposure":
            state.exposure = obs["exposure"]
            if (
                state.active_sku
                and state.active_sku not in state.investigated_skus
            ):
                state.investigated_skus.append(
                    state.active_sku
                )

            code = state.exposure.get("reason_code")
            missing = []

            if code == "LOT_INFORMATION_MISSING":
                missing.append(
                    "Company batch/lot evidence"
                )

            if code == "DATE_INFORMATION_MISSING":
                missing.append(
                    "Company use-by/best-before evidence"
                )

            if code in {
                "LOT_SCOPE_NOT_SPECIFIED",
                "DECISIVE_CONSTRAINT_MISSING",
            }:
                missing.append(
                    "Decisive recall lot/scope evidence"
                )

            if code == "PRODUCT_IDENTITY_UNCLEAR":
                missing.append(
                    "Reliable product identity evidence"
                )

            state.missing_evidence = missing

        elif tool == "get_inventory":
            state.inventory = obs

        elif tool == "get_dispatches":
            state.dispatches = obs

        elif tool == "get_purchase_history":
            state.purchase_history = obs

        elif tool == "resolve_company_exposure":
            state.candidates = obs.get("candidates") or []
            state.active_sku = obs.get("active_sku")
            state.batches = obs.get("batches") or []
            state.investigated_skus = list(obs.get("investigated_skus") or [])
            exposure = obs.get("exposure")
            if exposure is not None:
                self._apply_observation(
                    state,
                    "resolve_exposure",
                    {"ok": True, "exposure": exposure},
                )

        elif tool == "trace_internal_evidence":
            state.inventory = obs.get("inventory")
            state.dispatches = obs.get("dispatches")
            state.purchase_history = obs.get("purchase_history")

        elif tool == "open_response_case":
            state.case_id = obs["case_id"]
            state.case_action = obs.get("case_action")

        elif tool == "request_human_approval":
            if (
                obs.get("status")
                == "AWAITING_HUMAN_APPROVAL"
            ):
                state.status = (
                    "AWAITING_HUMAN_APPROVAL"
                )
                state.stop_reason = (
                    "HUMAN_APPROVAL_REQUIRED"
                )
            else:
                state.status = "COMPLETE"
                state.stop_reason = (
                    "NO_APPROVAL_REQUIRED"
                )

    def _remaining_candidate_skus(self, state):
        return [
            candidate.get("sku")
            for candidate in (state.candidates or [])
            if candidate.get("sku")
            and candidate.get("sku") not in state.investigated_skus
        ]

    def _complete_if_search_exhausted(self, state, last_tool):
        """
        Deterministically close a non-actionable catalogue investigation as
        soon as there are no plausible candidates left to inspect.

        This prevents a completed no-exposure investigation from consuming an
        extra planner cycle and incorrectly hitting MAX_AGENT_STEPS.
        """
        if state.status != "ACTIVE":
            return False

        if last_tool in {"search_catalogue", "resolve_company_exposure"} and not state.candidates:
            state.status = "COMPLETE"
            state.stop_reason = "NO_PLAUSIBLE_CATALOGUE_CANDIDATE"
            state.investigation_conclusion = "NO_ORGANISATIONAL_EXPOSURE_IDENTIFIED"
            state.log(
                "INVESTIGATION_COMPLETE",
                (
                    "No plausible company catalogue candidate was found. "
                    "No organisational exposure is identified from the available company evidence."
                ),
            )
            return True

        if last_tool not in {"resolve_exposure", "resolve_company_exposure"} or not state.exposure:
            return False

        if state.exposure.get("status") not in {
            "NOT_AFFECTED",
            "INSUFFICIENT_EVIDENCE",
        }:
            return False

        if self._remaining_candidate_skus(state):
            return False

        state.status = "COMPLETE"
        state.stop_reason = "CANDIDATE_SEARCH_EXHAUSTED"
        state.investigation_conclusion = "NO_ORGANISATIONAL_EXPOSURE_IDENTIFIED"
        state.log(
            "INVESTIGATION_COMPLETE",
            (
                f"All {len(state.investigated_skus)} retrieved catalogue candidate(s) "
                "were investigated and none established actionable organisational exposure."
            ),
        )
        return True

    def step(self, state):
        if state.status != "ACTIVE":
            return state

        if state.step >= self.max_steps:
            state.status = "STOPPED"
            state.stop_reason = (
                "MAX_AGENT_STEPS_REACHED"
            )
            state.log(
                "SAFETY_STOP",
                "Maximum bounded-agent step count reached.",
            )
            return state

        state.step += 1

        try:
            decision = self.planner.decide(state)
        except Exception as exc:
            state.status = "ERROR"
            state.stop_reason = "PLANNER_ERROR"
            state.log(
                "PLANNER_ERROR",
                str(exc),
            )
            return state

        state.planner_source = decision.get(
            "planner_source"
        )
        state.planner_model = decision.get(
            "planner_model"
        )

        summary = decision.get(
            "summary",
            "No summary supplied.",
        )
        action = decision.get("action")

        if action == "FINISH":
            state.status = "COMPLETE"
            state.stop_reason = "PLANNER_FINISHED"
            state.log("FINISH", summary)
            self.finalise(state)
            return state

        if action != "CALL_TOOL":
            state.status = "ERROR"
            state.stop_reason = (
                "INVALID_PLANNER_ACTION"
            )
            state.log(
                "ERROR",
                (
                    "Planner returned unsupported "
                    f"action: {action}"
                ),
            )
            return state

        tool = decision.get("tool")
        arguments = (
            decision.get("arguments") or {}
        )

        ok, error = validate_tool_call(
            tool,
            arguments,
        )
        if not ok:
            state.status = "ERROR"
            state.stop_reason = "POLICY_BLOCK"
            state.log(
                "POLICY_BLOCK",
                error or "Tool call blocked.",
                tool,
                arguments,
            )
            return state

        obs = execute_tool(
            self.ctx,
            tool,
            arguments,
        )
        state.log(
            "TOOL_CALL",
            summary,
            tool,
            arguments,
            obs,
        )
        self._apply_observation(
            state,
            tool,
            obs,
        )

        if state.status == "ACTIVE":
            self._complete_if_search_exhausted(
                state,
                tool,
            )

        if state.status != "ACTIVE":
            self.finalise(state)

        return state

    def _generate_evidence_gap_analysis(
        self,
        state,
    ):
        analyser = getattr(
            self.planner,
            "analyse_evidence_gap",
            None,
        )

        if (
            not callable(analyser)
            or not state.exposure
            or state.exposure.get("status")
            != "POSSIBLE"
            or state.status == "ERROR"
        ):
            return state

        try:
            analysis = analyser(state)
            if not analysis:
                return state

            state.evidence_gap_analysis = analysis
            state.log(
                "LLM_EVIDENCE_GAP_ANALYSIS",
                analysis.get(
                    "summary",
                    "LLM evidence-gap analysis generated.",
                ),
            )

            case = self.ctx.cases.get(
                state.case_id
            )
            if case:
                store_evidence_gap_analysis(
                    case,
                    analysis,
                    getattr(
                        self.planner,
                        "model",
                        "llm",
                    ),
                )
                self.ctx.save_case(case)

        except Exception as exc:
            state.log(
                "LLM_EVIDENCE_GAP_WARNING",
                str(exc),
            )

        return state

    def _generate_task_narratives(self, state):
        generator = getattr(
            self.planner,
            "generate_task_narratives",
            None,
        )
        case = self.ctx.cases.get(
            state.case_id
        )

        if (
            not callable(generator)
            or not case
            or not case.get("tasks")
            or state.status == "ERROR"
        ):
            return state

        try:
            narratives = generator(
                state,
                case.get("tasks") or [],
            )
            count = apply_task_narratives(
                case,
                narratives,
                getattr(
                    self.planner,
                    "model",
                    "llm",
                ),
            )
            state.llm_task_narratives_generated = (
                count
            )

            if count:
                self.ctx.save_case(case)
                state.log(
                    "LLM_TASK_NARRATIVES",
                    (
                        f"LLM generated case-specific "
                        f"rationale and suggested steps for "
                        f"{count} task(s)."
                    ),
                )

        except Exception as exc:
            # Deterministic task templates remain available as fallback.
            state.log(
                "LLM_TASK_NARRATIVE_WARNING",
                (
                    "LLM task wording failed; "
                    "deterministic templates were preserved. "
                    f"{exc}"
                ),
            )

        return state

    def _generate_recommendation(self, state):
        generator = getattr(
            self.planner,
            "generate_recommendation",
            None,
        )
        if not callable(generator):
            return state

        if (
            state.exposure is None
            or state.status == "ERROR"
        ):
            return state

        try:
            state.llm_recommendation = generator(
                state
            )
            state.log(
                "LLM_RECOMMENDATION",
                state.llm_recommendation.get(
                    "headline",
                    (
                        "LLM recommendation "
                        "generated."
                    ),
                ),
            )

            case = self.ctx.cases.get(
                state.case_id
            )
            if case:
                case["llm_recommendation"] = {
                    **state.llm_recommendation,
                    "model": getattr(
                        self.planner,
                        "model",
                        "llm",
                    ),
                    "generated_time": now_iso(),
                }
                add_event(
                    case,
                    "LLM_RECOMMENDATION_GENERATED",
                    "LLM",
                    {
                        "model": getattr(
                            self.planner,
                            "model",
                            "llm",
                        )
                    },
                )
                self.ctx.save_case(case)

        except Exception as exc:
            state.log(
                "LLM_RECOMMENDATION_WARNING",
                str(exc),
            )

        return state

    def finalise(self, state):
        if (
            state.status == "ACTIVE"
            or state.llm_enrichment_complete
        ):
            return state

        # LLM enrichment happens only after deterministic evidence and workflow
        # state have been established. It cannot modify classification or
        # governance fields. The fast Live Demo skips expensive task-narrative
        # generation because those full tasks are immediately replaced by the
        # two-decision pitch workflow; the advisory rationale is still generated.
        if self.enrichment_mode == "full":
            self._generate_evidence_gap_analysis(state)
            self._generate_task_narratives(state)
            self._generate_recommendation(state)
        elif self.enrichment_mode == "recommendation_only":
            self._generate_recommendation(state)
        elif self.enrichment_mode == "none":
            pass
        else:
            raise ValueError(f"Unknown enrichment_mode: {self.enrichment_mode}")
        state.llm_enrichment_complete = True
        return state

    def run(self, recall_id, on_step=None):
        """Run a bounded investigation to completion or a governed stop.

        ``on_step`` is an optional read-only presentation callback used by the
        Live Demo to reveal agent progress after each completed agent step.
        Existing callers can continue to call ``run(recall_id)`` unchanged.
        The callback receives the current ``InvestigationState`` and does not
        participate in planning, tool execution, matching, or governance.
        """
        state = self._initial_state(
            recall_id
        )
        state.log(
            "START",
            "Investigation started.",
        )

        while state.status == "ACTIVE":
            self.step(state)
            if on_step is not None:
                on_step(state)

        self.finalise(state)
        return state
