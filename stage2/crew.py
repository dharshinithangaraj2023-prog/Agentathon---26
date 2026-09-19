from typing import Optional, Dict, Any
from stage1.atlas import Atlas
from stage1.trace import DecisionTrace
from stage2.models import CycleResult, CrewState, ReviewReport
from stage2.memory import CrewMemory
from stage2.medical_review import MedicalReviewNode
from stage2.data_manager import DataManagerNode
from stage2.compliance import ComplianceNode
from stage2.human_gate import HumanGateNode


class ReviewCrew:
    """Multi-agent clinical, data, and compliance review crew with human gate."""

    def __init__(
        self,
        hub_url: Optional[str] = None,
        gateway_url: Optional[str] = None,
        team_key: Optional[str] = None,
        atlas: Optional[Atlas] = None,
        data_dir: Optional[str] = None,
        trace: Optional[DecisionTrace] = None,
        memory: Optional[CrewMemory] = None,
    ):
        self.hub_url = hub_url
        self.gateway_url = gateway_url
        self.team_key = team_key
        self.trace = trace or (atlas.trace if atlas else DecisionTrace())
        self.memory = memory or CrewMemory()

        # Initialize or link Atlas
        if atlas:
            self.atlas = atlas
        elif data_dir:
            self.atlas = Atlas(data_dir=data_dir, trace=self.trace)
        else:
            raise ValueError("Either atlas or data_dir must be provided to ReviewCrew.")

        # Initialize Nodes
        self.medical_review_node = MedicalReviewNode(
            query_service=self.atlas.query_service,
            memory=self.memory,
            trace=self.trace,
        )
        self.data_manager_node = DataManagerNode(
            data_dir=self.atlas.data_dir,
            query_service=self.atlas.query_service,
            memory=self.memory,
            trace=self.trace,
        )
        self.compliance_node = ComplianceNode(
            memory=self.memory,
            trace=self.trace,
        )
        self.human_gate_node = HumanGateNode(
            data_dir=self.atlas.data_dir,
            query_service=self.atlas.query_service,
            memory=self.memory,
            trace=self.trace,
        )

    def run_cycle(self, cut: int, protocol_version: Optional[int] = None) -> CycleResult:
        """
        Executes the 6 ReviewCrew nodes in strict, non-deviating sequence:
        1. detect
        2. medical_review
        3. data_manager
        4. compliance
        5. human_gate
        6. execute
        """
        if protocol_version is None:
            protocol_version = self.atlas.data_loader.get_protocol_version_for_cut(cut)

        # Initialize state object threaded through all nodes
        state = CrewState(cut=cut, protocol_version=protocol_version)

        # ---------------------------------------------------------------------
        # NODE 1 — DETECT (Uses Stage 1 ATLAS unchanged)
        # ---------------------------------------------------------------------
        state.raw_findings = self.atlas.run(cut=cut, protocol_version=protocol_version)
        state.node_history.append("detect")

        # Synchronize query_service references
        self.medical_review_node.qs = self.atlas.query_service
        self.data_manager_node.qs = self.atlas.query_service
        self.human_gate_node.qs = self.atlas.query_service

        # ---------------------------------------------------------------------
        # NODE 2 — MEDICAL REVIEW
        # ---------------------------------------------------------------------
        drafts, mon_count = self.medical_review_node.process_findings(
            findings=state.raw_findings,
            cut=cut,
            protocol_version=protocol_version,
        )
        state.escalation_drafts = drafts
        state.monitoring_count = mon_count
        state.node_history.append("medical_review")

        # ---------------------------------------------------------------------
        # NODE 3 — DATA MANAGER
        # ---------------------------------------------------------------------
        state.queries = self.data_manager_node.process_findings(
            findings=state.raw_findings,
            cut=cut,
            protocol_version=protocol_version,
        )
        state.node_history.append("data_manager")

        # ---------------------------------------------------------------------
        # NODE 4 — COMPLIANCE
        # ---------------------------------------------------------------------
        state.deviations = self.compliance_node.process_findings(
            findings=state.raw_findings,
            cut=cut,
            protocol_version=protocol_version,
        )
        state.node_history.append("compliance")

        # ---------------------------------------------------------------------
        # NODE 5 — HUMAN GATE
        # ---------------------------------------------------------------------
        state.processed_escalations = self.human_gate_node.process_escalations(
            escalations=state.escalation_drafts,
            cut=cut,
            protocol_version=protocol_version,
        )
        state.node_history.append("human_gate")

        # ---------------------------------------------------------------------
        # NODE 6 — EXECUTE
        # ---------------------------------------------------------------------
        state.node_history.append("execute")
        approved_count = len([e for e in state.processed_escalations if e.status == "APPROVED"])
        rejected_count = len([e for e in state.processed_escalations if e.status == "REJECTED"])
        clarify_count = len([e for e in state.processed_escalations if e.clarification_answer is not None])

        summary = {
            "cut": cut,
            "protocol_version": protocol_version,
            "total_raw_findings": len(state.raw_findings),
            "escalations_count": len(state.processed_escalations),
            "approved_escalations": approved_count,
            "rejected_escalations": rejected_count,
            "queries_dispatched": len(state.queries),
            "open_queries": len([q for q in state.queries if q.status == "OPEN"]),
            "closed_queries": len([q for q in state.queries if q.status == "CLOSED"]),
            "compliance_deviations": len(state.deviations),
            "monitoring_only_count": state.monitoring_count,
            "active_site_risks": len(self.memory.site_risks),
            "execution_order": state.node_history,
        }
        state.summary = summary

        trace_entries_for_cut = self.trace.get_by_cut(cut)
        review_report = ReviewReport(
            cut=cut,
            protocol_version=protocol_version,
            total_findings=len(state.raw_findings),
            escalations_submitted=len(state.processed_escalations),
            approved_count=approved_count,
            rejected_count=rejected_count,
            clarify_count=clarify_count,
            queries_raised=len(state.queries),
            deviations_logged=len(state.deviations),
            monitoring_count=state.monitoring_count,
            trace_entry_ids=[e.entry_id for e in trace_entries_for_cut],
            summary_text=f"Completed 6-node MONITOR cycle for Cut {cut} under Protocol v{protocol_version}.",
        )

        self.trace.record(
            cut=cut,
            protocol_version=protocol_version,
            node="execute",
            decision_id=f"DEC-EXEC-CUT{cut}",
            action="CYCLE_COMPLETED",
            reason=f"Successfully executed all 6 nodes for Cut {cut} under Protocol v{protocol_version}.",
            details=summary,
        )

        return CycleResult(
            cut=cut,
            protocol_version=protocol_version,
            findings_count=len(state.raw_findings),
            escalations=state.processed_escalations,
            queries=state.queries,
            deviations=state.deviations,
            monitoring_only_count=state.monitoring_count,
            report=review_report,
            summary=summary,
        )

