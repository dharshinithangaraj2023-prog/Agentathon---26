"""Stage 2 Node 2: Medical Review - Evaluates safety findings and drafts escalations."""
from typing import List, Tuple
from stage1.models import Finding
from stage1.graph import GraphQueryService
from stage1.trace import DecisionTrace
from stage2.models import Escalation
from stage2.memory import CrewMemory


class MedicalReviewNode:
    """Adjudicates clinical safety findings, separates monitoring vs escalation drafts."""

    def __init__(self, query_service: GraphQueryService, memory: CrewMemory, trace: DecisionTrace):
        self.qs = query_service
        self.memory = memory
        self.trace = trace

    def process_findings(self, findings: List[Finding], cut: int, protocol_version: int) -> Tuple[List[Escalation], int]:
        """
        Evaluate safety findings and produce escalation drafts.
        Returns (list_of_new_escalations, monitoring_only_count).
        """
        escalations: List[Escalation] = []
        monitoring_count = 0

        safety_findings = [f for f in findings if f.category == "safety"]

        for f in safety_findings:
            prior_cycles = self.memory.record_subject_flag(f.usubjid, cut)
            priority = 1 + prior_cycles

            # Check if this finding relates to Hy's Law
            if f.code == "HYS_LAW_CANDIDATE":
                # Check baseline/screening transaminases
                scr_labs = self.qs.get_screening_labs(f.usubjid)
                alt_scr = scr_labs.get("ALT")
                ast_scr = scr_labs.get("AST")

                # Baseline elevated condition check
                baseline_elevated = False
                if alt_scr and alt_scr.value_std and alt_scr.value_std > (2.0 * 56.0):
                    baseline_elevated = True
                if ast_scr and ast_scr.value_std and ast_scr.value_std > (2.0 * 40.0):
                    baseline_elevated = True

                if baseline_elevated:
                    # Baseline explains finding -> keep as monitoring only
                    monitoring_count += 1
                    self.trace.record(
                        cut=cut,
                        protocol_version=protocol_version,
                        node="medical_review",
                        decision_id=f"DEC-MED-MON-{f.usubjid}-HYS",
                        action="KEEP_MONITORING",
                        finding_id=f.finding_id,
                        subject=f.usubjid,
                        site=f.site,
                        reason=f"Hy's Law candidate kept as monitoring-only: Subject had baseline/screening transaminase elevation.",
                        evidence_refs=[e.model_dump() for e in f.evidence],
                        alternatives=["Immediate safety escalation to Medical Monitor"],
                    )
                    continue

            # Check if already rejected in past cycles
            temp_esc = Escalation(
                cut=cut,
                code=f.code,
                usubjid=f.usubjid,
                site=f.site,
                severity=f.severity,
                summary=f.rationale,
                rationale=f.rationale,
                evidence=f.evidence,
                alternatives=f.alternatives_considered or ["Downgrade to observational monitoring"],
                created_at_cut=cut,
                priority_level=priority,
            )
            temp_esc.compute_fingerprint()

            if self.memory.is_escalation_duplicate(temp_esc):
                monitoring_count += 1
                self.trace.record(
                    cut=cut,
                    protocol_version=protocol_version,
                    node="medical_review",
                    decision_id=f"DEC-MED-DEDUP-{f.usubjid}-{f.code}",
                    action="SUPPRESS_DUPLICATE_ESCALATION",
                    finding_id=f.finding_id,
                    subject=f.usubjid,
                    site=f.site,
                    reason=f"Escalation suppressed: Identical finding already escalated or rejected previously.",
                    evidence_refs=[e.model_dump() for e in f.evidence],
                )
                continue

            # Create new escalation draft
            self.memory.register_escalation(temp_esc)
            escalations.append(temp_esc)

            self.trace.record(
                cut=cut,
                protocol_version=protocol_version,
                node="medical_review",
                decision_id=f"DEC-MED-DRAFT-{temp_esc.escalation_id}",
                action="DRAFT_ESCALATION",
                finding_id=f.finding_id,
                subject=f.usubjid,
                site=f.site,
                reason=f"Drafted clinical escalation for serious safety finding '{f.code}'. Priority level: {priority}.",
                evidence_refs=[e.model_dump() for e in f.evidence],
                alternatives=temp_esc.alternatives,
                details={"priority": priority, "escalation_id": temp_esc.escalation_id},
            )

        if not safety_findings:
            self.trace.record(
                cut=cut,
                protocol_version=protocol_version,
                node="medical_review",
                decision_id=f"DEC-MED-SUMMARY-CUT{cut}",
                action="MONITORING_NO_ACTIONABLE_SAFETY",
                reason="No actionable critical safety signals in this cut; standard observational monitoring continued.",
                details={"safety_findings_count": 0, "monitoring_count": monitoring_count},
            )

        return escalations, monitoring_count


# Alias for Stage 2 class nomenclature
MedicalReview = MedicalReviewNode

