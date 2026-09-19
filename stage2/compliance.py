"""Stage 2 Node 4: Compliance - Audits deviations against active protocol version."""
from typing import List
from stage1.models import Finding
from stage1.trace import DecisionTrace
from stage2.models import Deviation
from stage2.memory import CrewMemory


class ComplianceNode:
    """Evaluates protocol deviations under the active protocol version."""

    def __init__(self, memory: CrewMemory, trace: DecisionTrace):
        self.memory = memory
        self.trace = trace

    def process_findings(self, findings: List[Finding], cut: int, protocol_version: int) -> List[Deviation]:
        """
        Record compliance deviations under the active protocol version.
        """
        deviations: List[Deviation] = []
        compliance_findings = [f for f in findings if f.category in ["compliance", "site"]]

        for f in compliance_findings:
            dev = Deviation(
                cut=cut,
                code=f.code,
                usubjid=f.usubjid,
                site=f.site,
                description=f.rationale,
                evidence=f.evidence,
                protocol_version=protocol_version,
                severity=f.severity,
            )
            deviations.append(dev)

            # Record site issue for risk profiling
            self.memory.record_site_issue(f.site, f.code)

            self.trace.record(
                cut=cut,
                protocol_version=protocol_version,
                node="compliance",
                decision_id=f"DEC-COMPL-{dev.deviation_id}",
                action="LOG_PROTOCOL_DEVIATION",
                finding_id=f.finding_id,
                subject=dev.usubjid,
                site=dev.site,
                reason=f"Logged protocol deviation under Protocol v{protocol_version}: {dev.description}",
                evidence_refs=[e.model_dump() for e in dev.evidence],
                details={"deviation_code": dev.code, "severity": dev.severity},
            )

        return deviations


# Alias for Stage 2 class nomenclature
ComplianceEngine = ComplianceNode

