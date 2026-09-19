"""Stage 3 - WATCH: 12-cut unattended surveillance system and explainability engine."""
import os
from typing import Dict, List, Any, Optional, Iterable
from stage1.trace import DecisionTrace
from stage2.crew import ReviewCrew
from stage2.models import CycleResult, Escalation
from stage3.models import Explanation, SurveillanceReport, AdversarialAlert, BudgetStatus
from stage3.budget import BudgetManager
from stage3.adversarial import AdversarialEngine
from stage3.incremental_graph import IncrementalGraphEngine
from stage3.explanation import ExplanationEngine
from stage3.reporting import ReportGenerator


class PendingEscalationStore:
    """Maintains cross-cut pending escalations and manages aging and standing limits."""

    def __init__(self, memory: CrewMemory, trace: DecisionTrace):
        self.memory = memory
        self.trace = trace

    def add_pending(self, escalation: Escalation):
        self.memory.register_escalation(escalation)

    def get_pending(self) -> List[Escalation]:
        return self.memory.get_pending_escalations()

    def update_status(self, escalation_id: str, status: str, response: str = ""):
        if escalation_id in self.memory.escalations_by_id:
            esc = self.memory.escalations_by_id[escalation_id]
            esc.status = status
            esc.monitor_response = response

    def age_pending_escalations(self, cut: int, protocol_version: int):
        """Handle 4-cut unanswered rule: log standing limits, never auto-approve or silently close."""
        pending = self.get_pending()
        for esc in pending:
            esc.cycles_pending = cut - esc.created_at_cut
            if esc.cycles_pending >= 4:
                self.trace.record(
                    cut=cut,
                    protocol_version=protocol_version,
                    node="human_gate",
                    decision_id=f"DEC-GATE-UNANSWERED-{esc.escalation_id}-CUT{cut}",
                    action="UNANSWERED_ESCALATION_STANDING_LIMITS",
                    finding_id=esc.code,
                    subject=esc.usubjid,
                    site=esc.site,
                    reason=(
                        f"Escalation {esc.escalation_id} has been pending for {esc.cycles_pending} cuts without human monitor reply. "
                        f"Continuing under standing limits. Gated safety action NOT executed; escalation preserved in pending queue."
                    ),
                    evidence_refs=[e.model_dump() for e in esc.evidence],
                    details={"cycles_pending": esc.cycles_pending, "created_at_cut": esc.created_at_cut},
                )


class StudyWatch:
    """Unattended 12-cut surveillance system with incremental graph updates and explainability."""

    def __init__(
        self,
        data_dir: str,
        crew: ReviewCrew,
        max_budget_seconds: float = 300.0,
        max_tokens: int = 100000,
    ):
        self.data_dir = data_dir
        self.crew = crew
        self.trace: DecisionTrace = crew.trace
        self.memory = crew.memory
        self.atlas = crew.atlas

        self.budget_manager = BudgetManager(max_seconds=max_budget_seconds, max_tokens=max_tokens)
        self.adversarial_engine = AdversarialEngine(trace=self.trace)
        self.incremental_engine = IncrementalGraphEngine(data_loader=self.atlas.data_loader, trace=self.trace)
        self.explanation_engine = ExplanationEngine(trace=self.trace)
        self.report_generator = ReportGenerator(trace=self.trace, memory=self.memory)
        self.pending_store = PendingEscalationStore(memory=self.memory, trace=self.trace)

        self.cycle_results: Dict[int, CycleResult] = {}
        self.adversarial_alerts: List[AdversarialAlert] = []
        self.latest_report: Optional[SurveillanceReport] = None

    def run_period(self, cuts: Iterable[int] = range(1, 13)) -> Dict[str, Any]:
        """
        Execute surveillance across the requested cut range sequentially,
        incrementally updating graph state, detecting adversarial patterns,
        and tracking delayed human responses.
        """
        self.budget_manager.start()
        cuts_list = list(cuts)
        os.makedirs("outputs", exist_ok=True)

        for cut in cuts_list:
            pv = self.atlas.data_loader.get_protocol_version_for_cut(cut)

            # 1. Budget tracking check
            budget_tier = self.budget_manager.get_tier()
            self.budget_manager.record_operation(f"cut_{cut}_execution", tokens=150, is_expensive=False)

            # 2. Incremental Graph Update
            if cut == 1:
                # Initial base graph build
                self.atlas.build(cut=1, protocol_version=pv)
            else:
                # Incremental synchronization with deltas and corrections
                delta_info = self.incremental_engine.apply_cut_delta(
                    graph=self.atlas.graph,
                    cut=cut,
                    protocol_version=pv,
                )
                self.budget_manager.record_operation("incremental_graph_sync", tokens=50)

            # 3. Adversarial and Data Integrity Screening
            alerts = self.adversarial_engine.run_all_checks(
                graph=self.atlas.graph,
                doc_manager=self.atlas.doc_manager,
                cut=cut,
                protocol_version=pv,
            )
            self.adversarial_alerts.extend(alerts)

            # 4. Handle Delayed Human Responses / Pending Escalations Aging
            self._manage_delayed_human_responses(cut, pv)

            # 5. Run Stage 2 Review Crew Cycle
            cycle_result = self.crew.run_cycle(cut=cut, protocol_version=pv)
            self.cycle_results[cut] = cycle_result

        # 6. Generate Non-Technical Surveillance Report
        budget_status = self.budget_manager.get_status()
        report = self.report_generator.generate_report(
            cuts=cuts_list,
            adversarial_alerts=self.adversarial_alerts,
            budget_status=budget_status,
            corrections_count=self.incremental_engine.applied_corrections_count,
        )
        self.latest_report = report

        # Persist report and trace to outputs/
        report_path = os.path.join("outputs", "surveillance_report.md")
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report.markdown_content)

        trace_path = os.path.join("outputs", "decision_trace.json")
        self.trace.export_json(trace_path)

        return {
            "cuts_evaluated": cuts_list,
            "cycle_results": self.cycle_results,
            "adversarial_alerts": self.adversarial_alerts,
            "applied_corrections": self.incremental_engine.applied_corrections_count,
            "budget_status": budget_status.model_dump(),
            "report_path": report_path,
            "trace_path": trace_path,
            "total_trace_entries": self.trace.count(),
        }

    def _manage_delayed_human_responses(self, cut: int, protocol_version: int):
        """Track pending escalations aging across cycles; handle the 4-cut unanswered expiration rule."""
        pending = self.memory.get_pending_escalations()
        for esc in pending:
            esc.cycles_pending = cut - esc.created_at_cut
            if esc.cycles_pending >= 4:
                # 4-cut unanswered rule: log standing limits, never auto-approve or silently close
                self.trace.record(
                    cut=cut,
                    protocol_version=protocol_version,
                    node="human_gate",
                    decision_id=f"DEC-GATE-UNANSWERED-{esc.escalation_id}-CUT{cut}",
                    action="UNANSWERED_ESCALATION_STANDING_LIMITS",
                    finding_id=esc.code,
                    subject=esc.usubjid,
                    site=esc.site,
                    reason=(
                        f"Escalation {esc.escalation_id} has been pending for {esc.cycles_pending} cuts without human monitor reply. "
                        f"Continuing under standing limits. Gated safety action NOT executed; escalation preserved in pending queue."
                    ),
                    evidence_refs=[e.model_dump() for e in esc.evidence],
                    details={"cycles_pending": esc.cycles_pending, "created_at_cut": esc.created_at_cut},
                )

    def explain(self, decision_id: str) -> Explanation:
        """Explain a decision based ONLY on recorded immutable trace evidence."""
        return self.explanation_engine.explain(decision_id)
