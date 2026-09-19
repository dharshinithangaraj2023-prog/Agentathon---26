"""Typed data models for Stage 2 (MONITOR) crew, memory, queries, and escalations."""
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from stage1.models import EvidenceRef, Finding
import hashlib
import uuid


class Query(BaseModel):
    """Data quality query raised to investigative site."""
    query_id: str = Field(default_factory=lambda: f"Q-{uuid.uuid4().hex[:8]}")
    cut: int
    domain: str
    usubjid: str
    seq: int
    issue_code: str
    text: str
    status: str = "OPEN"  # OPEN, CLOSED, UNANSWERED, ANSWERED
    response: Optional[str] = None
    fingerprint: str = ""

    def compute_fingerprint(self) -> str:
        raw = f"{self.domain}|{self.usubjid}|{self.seq}|{self.issue_code}"
        self.fingerprint = hashlib.md5(raw.encode("utf-8")).hexdigest()
        return self.fingerprint


class Escalation(BaseModel):
    """Safety or critical finding escalation submitted to Medical Monitor."""
    escalation_id: str = Field(default_factory=lambda: f"ESC-{uuid.uuid4().hex[:8]}")
    cut: int
    code: str
    usubjid: str
    site: str
    severity: str  # CRITICAL, HIGH, MONITORING
    summary: str
    rationale: str
    evidence: List[EvidenceRef] = Field(default_factory=list)
    alternatives: List[str] = Field(default_factory=list)
    status: str = "PENDING"  # PENDING, APPROVED, REJECTED, CLARIFY, MONITORING, EXPIRED
    monitor_response: Optional[str] = None
    clarification_question: Optional[str] = None
    clarification_answer: Optional[str] = None
    action_taken: Optional[str] = None
    created_at_cut: int = 1
    cycles_pending: int = 0
    priority_level: int = 1
    fingerprint: str = ""

    def compute_fingerprint(self) -> str:
        ev_str = ",".join(sorted([e.to_key() for e in self.evidence]))
        raw = f"{self.code}|{self.usubjid}|{ev_str}"
        self.fingerprint = hashlib.md5(raw.encode("utf-8")).hexdigest()
        return self.fingerprint


class Deviation(BaseModel):
    """Protocol compliance deviation."""
    deviation_id: str = Field(default_factory=lambda: f"DEV-{uuid.uuid4().hex[:8]}")
    cut: int
    code: str
    usubjid: str
    site: str
    description: str
    evidence: List[EvidenceRef] = Field(default_factory=list)
    protocol_version: int
    severity: str = "MEDIUM"


class CrewState(BaseModel):
    """State object sequentially threaded through all 6 ReviewCrew nodes."""
    cut: int
    protocol_version: int
    raw_findings: List[Finding] = Field(default_factory=list)
    escalation_drafts: List[Escalation] = Field(default_factory=list)
    queries: List[Query] = Field(default_factory=list)
    deviations: List[Deviation] = Field(default_factory=list)
    processed_escalations: List[Escalation] = Field(default_factory=list)
    monitoring_count: int = 0
    node_history: List[str] = Field(default_factory=list)
    summary: Dict[str, Any] = Field(default_factory=dict)


class ReviewReport(BaseModel):
    """Detailed cycle review report generated at the execute node."""
    cut: int
    protocol_version: int
    total_findings: int
    escalations_submitted: int
    approved_count: int
    rejected_count: int
    clarify_count: int
    queries_raised: int
    deviations_logged: int
    monitoring_count: int
    trace_entry_ids: List[str] = Field(default_factory=list)
    summary_text: str = ""


class CycleResult(BaseModel):
    """Summary of a single MONITOR cycle execution."""
    cut: int
    protocol_version: int
    findings_count: int
    escalations: List[Escalation] = Field(default_factory=list)
    queries: List[Query] = Field(default_factory=list)
    deviations: List[Deviation] = Field(default_factory=list)
    monitoring_only_count: int = 0
    report: Optional[ReviewReport] = None
    summary: Dict[str, Any] = Field(default_factory=dict)

