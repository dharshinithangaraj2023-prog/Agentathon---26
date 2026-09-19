"""Typed data models for Stage 3 (WATCH), explainability, reporting, and adversarial detection."""
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class Explanation(BaseModel):
    """Complete, auditable explanation resolved directly from the decision trace."""
    decision_id: str
    what: str
    evidence: List[Dict[str, Any]] = Field(default_factory=list)
    evidence_lines: List[str] = Field(default_factory=list)
    evidence_refs: List[Dict[str, Any]] = Field(default_factory=list)
    alternatives: List[str] = Field(default_factory=list)
    why: str
    node: str
    cut: int
    protocol_version: int
    timestamp: str
    trace_entry_ids: List[str] = Field(default_factory=list)
    consistent_with_trace: bool = True


class AdversarialAlert(BaseModel):
    """Alert for detected adversarial data, unit shifts, or document tampering."""
    alert_type: str  # SITE_REGULARITY_ANOMALY | DATA_INTEGRITY_LAB_UNIT_SHIFT | DOCUMENT_CHANGED | AUTOMATED_INSTRUCTION_IGNORED
    site_id: Optional[str] = None
    cut: int
    description: str
    evidence: List[Dict[str, Any]] = Field(default_factory=list)
    quarantined_records: int = 0
    confidence: float = 1.0
    action_taken: str = "QUARANTINE_AND_NOTIFY"


class BudgetStatus(BaseModel):
    """Current global computation and token budget state."""
    tier: str = "FULL"  # FULL | REDUCED | MINIMAL
    elapsed_seconds: float = 0.0
    max_seconds: float = 300.0
    tokens_used: int = 0
    max_tokens: int = 100000
    expensive_ops_count: int = 0
    percent_consumed: float = 0.0


class SurveillanceReport(BaseModel):
    """Complete clinical surveillance report across cuts."""
    study_id: str = "STUDY-042"
    cuts_evaluated: List[int] = Field(default_factory=list)
    executive_summary: str = ""
    safety_summary: str = ""
    data_quality_summary: str = ""
    compliance_summary: str = ""
    site_risk_summary: str = ""
    adversarial_summary: str = ""
    human_decisions_summary: str = ""
    budget_summary: str = ""
    markdown_content: str = ""
