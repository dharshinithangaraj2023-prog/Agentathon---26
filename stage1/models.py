"""Core typed data models for Stage 1 (ATLAS) and study entities."""
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
import hashlib


class EvidenceRef(BaseModel):
    """Normalized evidence pointer referencing a specific clinical record."""
    domain: str
    usubjid: str
    seq: int

    def to_key(self) -> str:
        return f"{self.domain}|{self.usubjid}|{self.seq}"


class Finding(BaseModel):
    """Normalized finding representation produced by ATLAS detectors."""
    finding_id: str
    code: str
    usubjid: str
    site: str
    severity: str  # CRITICAL, HIGH, MEDIUM, LOW, MONITORING
    category: str  # safety | data_quality | compliance | site
    rationale: str
    evidence: List[EvidenceRef] = Field(default_factory=list)
    cut: int
    protocol_version: int
    status: str = "OPEN"  # OPEN, RESOLVED, QUARANTINED, MONITORING_ONLY
    alternatives_considered: List[str] = Field(default_factory=list)

    def fingerprint(self) -> str:
        """Deterministic fingerprint for deduplication across cycles."""
        ev_str = ",".join(sorted([e.to_key() for e in self.evidence]))
        raw = f"{self.code}|{self.usubjid}|{self.category}|{ev_str}"
        return hashlib.md5(raw.encode("utf-8")).hexdigest()


class Subject(BaseModel):
    usubjid: str
    siteid: str
    country: Optional[str] = None
    age: Optional[float] = None
    sex: Optional[str] = None
    dminit: Optional[str] = None
    brthdtc: Optional[str] = None
    arm: Optional[str] = None
    rfstdtc: Optional[str] = None  # First dose date
    scr_hba1c: Optional[float] = None
    cut_available: int = 1
    corrected_at_cut: Optional[int] = None
    quarantined: bool = False


class AdverseEvent(BaseModel):
    usubjid: str
    seq: int
    term: str
    severity: Optional[str] = None  # MILD, MODERATE, SEVERE
    serious: str = "N"  # AESER
    hospitalisation: str = "N"  # AESHOSP
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    outcome: Optional[str] = None
    narrative: Optional[str] = None
    cut_available: int = 1
    corrected_at_cut: Optional[int] = None
    quarantined: bool = False


class LabResult(BaseModel):
    usubjid: str
    seq: int
    visit: Optional[str] = None
    date: Optional[str] = None
    test_code: str  # ALT, AST, BILI, HBA1C, GLUC, CREAT, etc.
    value_raw: Optional[str] = None
    unit_raw: Optional[str] = None
    value_num: Optional[float] = None
    unit_std: Optional[str] = None
    value_std: Optional[float] = None  # Normalized to conventional central units
    cut_available: int = 1
    corrected_at_cut: Optional[int] = None
    quarantined: bool = False
    is_reissued: bool = False


class VitalSign(BaseModel):
    usubjid: str
    seq: int
    visit: Optional[str] = None
    date: Optional[str] = None
    test_code: str
    value_raw: Optional[str] = None
    unit_raw: Optional[str] = None
    value_num: Optional[float] = None
    cut_available: int = 1
    corrected_at_cut: Optional[int] = None
    quarantined: bool = False


class Dose(BaseModel):
    usubjid: str
    seq: int
    dose: Optional[float] = None
    dose_unit: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    cut_available: int = 1
    corrected_at_cut: Optional[int] = None
    quarantined: bool = False


class Medication(BaseModel):
    usubjid: str
    seq: int
    name: Optional[str] = None
    class_name: Optional[str] = None  # CMCLAS
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    cut_available: int = 1
    corrected_at_cut: Optional[int] = None
    quarantined: bool = False


class Disposition(BaseModel):
    usubjid: str
    seq: int
    term: Optional[str] = None
    decod: Optional[str] = None
    date: Optional[str] = None
    cut_available: int = 1
    corrected_at_cut: Optional[int] = None


class MedicalHistory(BaseModel):
    usubjid: str
    seq: int
    term: Optional[str] = None
    decod: Optional[str] = None
    cut_available: int = 1
    corrected_at_cut: Optional[int] = None


class ECG(BaseModel):
    usubjid: str
    seq: int
    visit: Optional[str] = None
    date: Optional[str] = None
    test_code: str
    value_raw: Optional[str] = None
    unit_raw: Optional[str] = None
    value_num: Optional[float] = None
    cut_available: int = 1
    corrected_at_cut: Optional[int] = None


class ProtocolRule(BaseModel):
    protocol_version: int
    rule_name: str
    rule_type: str  # inclusion, exclusion, visit_window, prohibited_med, dosing
    parameters: Dict[str, Any] = Field(default_factory=dict)
    effective_from_cut: int = 1


class DocumentMetadata(BaseModel):
    doc_name: str
    version: Optional[str] = None
    hash_sha256: str
    previous_hash: Optional[str] = None
    has_tampered_instructions: bool = False
    ignored_instructions: List[str] = Field(default_factory=list)
    effective_cut: int = 1
