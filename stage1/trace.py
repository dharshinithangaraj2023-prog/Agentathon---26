"""Append-only audit decision trace implementation."""
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from pydantic import BaseModel, Field
import json
import uuid


class TraceEntry(BaseModel):
    """Immutable single step audit trace record."""
    entry_id: str = Field(default_factory=lambda: f"TR-{uuid.uuid4().hex[:8]}")
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    cut: int
    protocol_version: int
    node: str  # detect, medical_review, data_manager, compliance, human_gate, execute, watch, adversarial
    decision_id: str
    action: str
    finding_id: Optional[str] = None
    subject: Optional[str] = None
    site: Optional[str] = None
    reason: str
    evidence_lines: List[str] = Field(default_factory=list)
    evidence_refs: List[Dict[str, Any]] = Field(default_factory=list)  # [{'domain': '...', 'usubjid': '...', 'seq': ...}]
    alternatives: List[str] = Field(default_factory=list)
    details: Dict[str, Any] = Field(default_factory=dict)


class DecisionTrace:
    """In-memory append-only decision log providing auditability and explain() resolution."""

    def __init__(self):
        self._entries: List[TraceEntry] = []
        self._by_decision_id: Dict[str, TraceEntry] = {}

    def append(self, entry: TraceEntry) -> TraceEntry:
        """Append an immutable entry to the trace."""
        self._entries.append(entry)
        if entry.decision_id:
            self._by_decision_id[entry.decision_id] = entry
        return entry

    def record(
        self,
        cut: int,
        protocol_version: int,
        node: str,
        decision_id: str,
        action: str,
        reason: str,
        finding_id: Optional[str] = None,
        subject: Optional[str] = None,
        site: Optional[str] = None,
        evidence_lines: Optional[List[str]] = None,
        evidence_refs: Optional[List[Dict[str, Any]]] = None,
        alternatives: Optional[List[str]] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> TraceEntry:
        """Convenience method to construct and record a trace entry immediately."""
        entry = TraceEntry(
            cut=cut,
            protocol_version=protocol_version,
            node=node,
            decision_id=decision_id,
            action=action,
            finding_id=finding_id,
            subject=subject,
            site=site,
            reason=reason,
            evidence_lines=evidence_lines or [],
            evidence_refs=evidence_refs or [],
            alternatives=alternatives or [],
            details=details or {},
        )
        return self.append(entry)

    def get_by_decision_id(self, decision_id: str) -> Optional[TraceEntry]:
        return self._by_decision_id.get(decision_id)

    def get_by_cut(self, cut: int) -> List[TraceEntry]:
        return [e for e in self._entries if e.cut == cut]

    def get_by_subject(self, usubjid: str) -> List[TraceEntry]:
        return [e for e in self._entries if e.subject == usubjid]

    def get_all(self) -> List[TraceEntry]:
        return list(self._entries)

    def count(self) -> int:
        return len(self._entries)

    def export_dict(self) -> List[Dict[str, Any]]:
        return [e.model_dump() for e in self._entries]

    def export_json(self, filepath: str):
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(self.export_dict(), f, indent=2)
