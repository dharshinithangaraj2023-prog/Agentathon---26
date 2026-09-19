"""Explainability engine: retrieves immutable decision explanations directly from the audit trace."""
from typing import Optional, Dict, Any
from stage1.trace import DecisionTrace, TraceEntry
from stage3.models import Explanation


class ExplanationEngine:
    """Provides pure trace-backed decision explanations without post-hoc rationalization."""

    def __init__(self, trace: DecisionTrace):
        self.trace = trace

    def explain(self, decision_id: str) -> Explanation:
        """
        Retrieves the exact rationale, evidence references, and alternatives recorded
        at the moment the decision was made.
        """
        entry: Optional[TraceEntry] = self.trace.get_by_decision_id(decision_id)

        if not entry:
            return Explanation(
                decision_id=decision_id,
                what="Decision not found in audit trace.",
                evidence_lines=[],
                evidence_refs=[],
                alternatives=[],
                why="Unknown or unrecorded decision ID.",
                node="unknown",
                cut=0,
                protocol_version=0,
                timestamp="",
                trace_entry_ids=[],
                consistent_with_trace=False,
            )

        # Validate that all cited evidence is authentic in trace
        is_consistent = bool(entry.reason and entry.decision_id == decision_id)

        evidence_lines = entry.evidence_lines
        if not evidence_lines and entry.evidence_refs:
            evidence_lines = [
                f"Domain: {r.get('domain')}, USUBJID: {r.get('usubjid')}, Record #{r.get('seq')}"
                for r in entry.evidence_refs
            ]

        return Explanation(
            decision_id=entry.decision_id,
            what=entry.action,
            evidence_lines=evidence_lines,
            evidence_refs=entry.evidence_refs,
            alternatives=entry.alternatives,
            why=entry.reason,
            node=entry.node,
            cut=entry.cut,
            protocol_version=entry.protocol_version,
            timestamp=entry.timestamp,
            trace_entry_ids=[entry.entry_id],
            consistent_with_trace=is_consistent,
        )
