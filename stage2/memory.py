"""Persistent memory maintaining cross-cycle state, fingerprints, and site risk."""
from typing import Dict, List, Set, Any, Optional
from stage2.models import Query, Escalation


class CrewMemory:
    """Persistent state across MONITOR cycles to guarantee deduplication and track history."""

    def __init__(self):
        self.query_fingerprints: Set[str] = set()
        self.escalation_fingerprints: Set[str] = set()
        self.rejected_escalation_fingerprints: Set[str] = set()
        self.rejected_reasons: Dict[str, str] = {}

        # Subject and site historical tracking
        self.subject_flagged_cuts: Dict[str, Set[int]] = {}  # usubjid -> set of cuts
        self.site_issue_counts: Dict[str, int] = {}          # site_id -> total issues
        self.site_risks: Dict[str, Dict[str, Any]] = {}      # site_id -> metadata

        # Active item tracking
        self.queries_by_id: Dict[str, Query] = {}
        self.escalations_by_id: Dict[str, Escalation] = {}

    def is_query_duplicate(self, query: Query) -> bool:
        """Return True if an identical query was already raised previously."""
        fp = query.compute_fingerprint()
        return fp in self.query_fingerprints

    def register_query(self, query: Query):
        """Save query and register its fingerprint."""
        fp = query.compute_fingerprint()
        self.query_fingerprints.add(fp)
        self.queries_by_id[query.query_id] = query

    def is_escalation_duplicate(self, esc: Escalation) -> bool:
        """Return True if this escalation was already created or is previously rejected."""
        fp = esc.compute_fingerprint()
        if fp in self.rejected_escalation_fingerprints:
            return True
        return fp in self.escalation_fingerprints

    def register_escalation(self, esc: Escalation):
        """Save escalation and register its fingerprint."""
        fp = esc.compute_fingerprint()
        self.escalation_fingerprints.add(fp)
        self.escalations_by_id[esc.escalation_id] = esc

    def is_escalation_rejected_previously(self, fingerprint: str) -> bool:
        return fingerprint in self.rejected_escalation_fingerprints

    def mark_escalation_rejected(self, esc: Escalation, reason: str):
        """Record human rejection to prevent future duplicate escalations."""
        fp = esc.compute_fingerprint()
        self.rejected_escalation_fingerprints.add(fp)
        self.rejected_reasons[fp] = reason
        esc.status = "REJECTED"
        esc.monitor_response = reason

    def record_subject_flag(self, usubjid: str, cut: int) -> int:
        """
        Record that a subject had a finding at this cut.
        Returns the number of prior distinct cycles the subject was flagged in.
        """
        if usubjid not in self.subject_flagged_cuts:
            self.subject_flagged_cuts[usubjid] = set()
        prior_count = len([c for c in self.subject_flagged_cuts[usubjid] if c < cut])
        self.subject_flagged_cuts[usubjid].add(cut)
        return prior_count

    def record_site_issue(self, site_id: str, issue_code: str):
        """Increment issue count for a site and update site risk score."""
        self.site_issue_counts[site_id] = self.site_issue_counts.get(site_id, 0) + 1
        count = self.site_issue_counts[site_id]

        risk_level = "LOW"
        if count >= 8:
            risk_level = "HIGH"
        elif count >= 4:
            risk_level = "MEDIUM"

        self.site_risks[site_id] = {
            "site_id": site_id,
            "total_issues": count,
            "risk_level": risk_level,
            "last_issue": issue_code,
        }

    def get_open_queries(self) -> List[Query]:
        return [q for q in self.queries_by_id.values() if q.status == "OPEN"]

    def get_pending_escalations(self) -> List[Escalation]:
        return [e for e in self.escalations_by_id.values() if e.status == "PENDING"]

    def get_all_queries(self) -> List[Query]:
        return list(self.queries_by_id.values())

    def get_all_escalations(self) -> List[Escalation]:
        return list(self.escalations_by_id.values())
