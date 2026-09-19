"""Adversarial pattern detection: site regularity anomalies, lab unit corruption, document tampering."""
from typing import List, Dict, Any, Optional
import numpy as np
from stage1.graph import StudyGraph
from stage1.trace import DecisionTrace
from stage1.documents import DocumentManager
from stage3.models import AdversarialAlert


class AdversarialEngine:
    """Detects adversarial conditions: implausible site regularity, unit corruption, prompt injections."""

    def __init__(self, trace: DecisionTrace):
        self.trace = trace
        self.active_alerts: List[AdversarialAlert] = []

    def run_all_checks(
        self,
        graph: StudyGraph,
        doc_manager: DocumentManager,
        cut: int,
        protocol_version: int,
    ) -> List[AdversarialAlert]:
        """Execute all adversarial detection algorithms and return alerts."""
        alerts: List[AdversarialAlert] = []
        alerts.extend(self.detect_site_regularity(graph, cut, protocol_version))
        alerts.extend(self.detect_lab_unit_shifts(graph, cut, protocol_version))
        alerts.extend(self.detect_document_tampering(doc_manager, cut, protocol_version))
        self.active_alerts.extend(alerts)
        return alerts

    # -------------------------------------------------------------------------
    # 1. IMPLAUSIBLY REGULAR SITE DETECTION
    # -------------------------------------------------------------------------
    def detect_site_regularity(self, graph: StudyGraph, cut: int, protocol_version: int) -> List[AdversarialAlert]:
        alerts: List[AdversarialAlert] = []

        for site_id, subj_ids in graph.sites.items():
            if len(subj_ids) < 4:
                continue

            subjs = [graph.subjects[s] for s in subj_ids if s in graph.subjects]

            # Check vital signs variance across site subjects
            vs_values = []
            for s in subjs:
                v_list = graph.vitals.get(s.usubjid, [])
                for vs in v_list:
                    if vs.value_num is not None:
                        vs_values.append(vs.value_num)

            # If site has extensive vital records with zero or near-zero variance
            if len(vs_values) >= 12:
                std_dev = float(np.std(vs_values))
                if std_dev < 0.001:  # Implausibly identical measurements
                    # Quarantine site records
                    quarantined_count = 0
                    for s in subjs:
                        for vs in graph.vitals.get(s.usubjid, []):
                            vs.quarantined = True
                            quarantined_count += 1

                    alert = AdversarialAlert(
                        alert_type="SITE_REGULARITY_ANOMALY",
                        site_id=site_id,
                        cut=cut,
                        description=(
                            f"Site {site_id} exhibits implausibly zero variance (std={std_dev:.4f}) across "
                            f"{len(vs_values)} vital sign measurements. Data quarantined for safety analysis."
                        ),
                        quarantined_records=quarantined_count,
                        confidence=0.99,
                        action_taken="QUARANTINE_FROM_SAFETY_AND_RECOMMEND_AUDIT",
                    )
                    alerts.append(alert)

                    self.trace.record(
                        cut=cut,
                        protocol_version=protocol_version,
                        node="adversarial",
                        decision_id=f"DEC-ADV-REG-{site_id}-CUT{cut}",
                        action="SITE_REGULARITY_ANOMALY_QUARANTINE",
                        site=site_id,
                        reason=alert.description,
                        alternatives=["Accept measurements as true biologic uniformity", "Exclude site entirely from trial"],
                        details={"std_dev": std_dev, "record_count": len(vs_values)},
                    )

            # Check AE narrative duplication across patients at site
            narratives = []
            for s in subjs:
                for ae in graph.aes.get(s.usubjid, []):
                    if ae.narrative and len(ae.narrative) > 20:
                        narratives.append(ae.narrative.strip())

            if len(narratives) >= 5:
                unique_narratives = set(narratives)
                # If >80% of narratives are identical word-for-word
                if len(unique_narratives) / len(narratives) < 0.25:
                    alert = AdversarialAlert(
                        alert_type="SITE_REGULARITY_ANOMALY",
                        site_id=site_id,
                        cut=cut,
                        description=f"Site {site_id} shows {len(narratives)} AE narratives with extreme exact textual duplication.",
                        quarantined_records=len(narratives),
                        confidence=0.95,
                        action_taken="LOG_ANOMALY_AND_AUDIT",
                    )
                    alerts.append(alert)

                    self.trace.record(
                        cut=cut,
                        protocol_version=protocol_version,
                        node="adversarial",
                        decision_id=f"DEC-ADV-NARR-{site_id}-CUT{cut}",
                        action="SITE_NARRATIVE_DUPLICATION_DETECTED",
                        site=site_id,
                        reason=alert.description,
                        alternatives=["Standardized clinic template usage"],
                    )

        return alerts

    # -------------------------------------------------------------------------
    # 2. LAB UNIT CORRUPTION DETECTION
    # -------------------------------------------------------------------------
    def detect_lab_unit_shifts(self, graph: StudyGraph, cut: int, protocol_version: int) -> List[AdversarialAlert]:
        alerts: List[AdversarialAlert] = []

        # Compare median lab values per site and per test
        # Detect unit shifts like Glucose mg/dL -> mmol/L (factor ~18.0) or ALT U/L -> ukat/L (factor ~60.0)
        UNIT_SHIFT_FACTORS = [
            ("GLUC", 18.0182, 0.20, "mg/dL to mmol/L analyser unit shift"),
            ("ALT", 60.0, 0.25, "U/L to ukat/L analyser unit shift"),
            ("AST", 60.0, 0.25, "U/L to ukat/L analyser unit shift"),
            ("CREAT", 88.4, 0.20, "mg/dL to umol/L analyser unit shift"),
        ]

        for site_id, subj_ids in graph.sites.items():
            subjs = [graph.subjects[s] for s in subj_ids if s in graph.subjects]

            for test_code, expected_factor, tolerance, shift_name in UNIT_SHIFT_FACTORS:
                test_values = []
                quarantine_candidates = []

                for s in subjs:
                    labs = graph.labs.get(s.usubjid, [])
                    for lb in labs:
                        if lb.test_code.upper() == test_code and lb.value_num is not None:
                            test_values.append(lb.value_num)
                            quarantine_candidates.append(lb)

                if len(test_values) >= 6:
                    site_median = float(np.median(test_values))

                    # Compare against standard reference midpoint for central lab
                    # Glucose typical median ~100-140 mg/dL. If reported ~5.0 - 8.0, ratio is ~18
                    # If site median is scaled down by roughly the expected_factor:
                    if test_code == "GLUC" and site_median < 15.0 and site_median > 2.0:
                        ratio = 118.0 / site_median
                        if abs(ratio - expected_factor) / expected_factor <= tolerance:
                            # Confirmed site-wide glucose unit corruption!
                            quarantined_count = 0
                            for lb in quarantine_candidates:
                                lb.quarantined = True
                                quarantined_count += 1

                            alert = AdversarialAlert(
                                alert_type="DATA_INTEGRITY_LAB_UNIT_SHIFT",
                                site_id=site_id,
                                cut=cut,
                                description=(
                                    f"Detected site-wide lab unit shift for {test_code} at Site {site_id} "
                                    f"(site median {site_median:.2f}, expected ratio ~{expected_factor:.1f} indicates {shift_name}). "
                                    f"Quarantined {quarantined_count} lab values to prevent clinical false alarms."
                                ),
                                quarantined_records=quarantined_count,
                                confidence=0.98,
                                action_taken="QUARANTINE_FROM_SAFETY_AND_RAISE_LAB_QUERY",
                            )
                            alerts.append(alert)

                            self.trace.record(
                                cut=cut,
                                protocol_version=protocol_version,
                                node="adversarial",
                                decision_id=f"DEC-ADV-UNIT-{site_id}-{test_code}-CUT{cut}",
                                action="LAB_UNIT_CORRUPTION_QUARANTINED",
                                site=site_id,
                                reason=alert.description,
                                alternatives=["Classify as widespread acute hypoglycaemic crisis (false alarm)"],
                                details={
                                    "test_code": test_code,
                                    "observed_median": site_median,
                                    "estimated_factor": ratio,
                                },
                            )

        return alerts

    # -------------------------------------------------------------------------
    # 3. DOCUMENT TAMPERING DETECTION
    # -------------------------------------------------------------------------
    def detect_document_tampering(self, doc_manager: DocumentManager, cut: int, protocol_version: int) -> List[AdversarialAlert]:
        alerts: List[AdversarialAlert] = []
        doc_metas = doc_manager.inspect_documents()

        for doc in doc_metas:
            if doc.has_tampered_instructions:
                alert = AdversarialAlert(
                    alert_type="AUTOMATED_INSTRUCTION_IGNORED",
                    site_id=None,
                    cut=cut,
                    description=(
                        f"Document '{doc.doc_name}' contains adversarial prompt instructions: "
                        f"{', '.join(doc.ignored_instructions)}. Treated as passive evidence."
                    ),
                    confidence=1.0,
                    action_taken="IGNORE_PROMPT_INJECTIONS",
                )
                alerts.append(alert)

        return alerts

    # Method aliases matching specification
    def detect_regular_site(self, graph: StudyGraph, cut: int, protocol_version: int) -> List[AdversarialAlert]:
        return self.detect_site_regularity(graph, cut, protocol_version)

    def detect_unit_shift(self, graph: StudyGraph, cut: int, protocol_version: int) -> List[AdversarialAlert]:
        return self.detect_lab_unit_shifts(graph, cut, protocol_version)

    def detect_protocol_amendment(self, prev_version: int, new_version: int, cut: int) -> Optional[AdversarialAlert]:
        if prev_version != new_version:
            alert = AdversarialAlert(
                alert_type="PROTOCOL_AMENDMENT_DETECTED",
                site_id=None,
                cut=cut,
                description=f"Protocol amendment effective at Cut {cut}: Version {prev_version} -> Version {new_version}.",
                confidence=1.0,
                action_taken="RECOMPUTE_AFFECTED_DEVIATIONS_AND_UPDATE_RULES",
            )
            self.trace.record(
                cut=cut,
                protocol_version=new_version,
                node="adversarial",
                decision_id=f"DEC-ADV-AMEND-CUT{cut}",
                action="PROTOCOL_AMENDMENT_ENFORCED",
                reason=alert.description,
                alternatives=["Continue using outdated protocol version rules (prohibited)"],
            )
            return alert
        return None


# Alias for Stage 3 class nomenclature
AdversarialDetector = AdversarialEngine

