"""Generic finding detectors for Safety, Data Quality, Compliance, and Site Risk."""
from typing import List, Dict, Any, Optional
from datetime import datetime
from stage1.models import Finding, EvidenceRef
from stage1.graph import StudyGraph, GraphQueryService


class DetectorEngine:
    """Evaluates generic clinical, data quality, compliance, and safety rules over the graph."""

    SCHEDULED_VISIT_DAYS = {
        "SCREENING": -14,
        "BASELINE": 0,
        "WEEK 2": 14,
        "WEEK 4": 28,
        "WEEK 8": 56,
        "WEEK 12": 84,
        "WEEK 16": 112,
        "WEEK 20": 140,
        "WEEK 24": 168,
        "END OF STUDY": 182,
        "EOS": 182,
    }

    def __init__(self, query_service: GraphQueryService, reference_ranges: Dict[str, Dict[str, Any]], rules: Dict[str, Any]):
        self.qs = query_service
        self.ranges = reference_ranges
        self.rules = rules
        self.protocol_version = rules.get("version", 1)

    def run_all(self, cut: int) -> List[Finding]:
        """Execute all detector categories and return normalized Finding objects."""
        findings: List[Finding] = []
        findings.extend(self.detect_safety_signals(cut))
        findings.extend(self.detect_data_quality(cut))
        findings.extend(self.detect_compliance_deviations(cut))
        findings.extend(self.detect_site_level_patterns(cut))
        return findings

    # -------------------------------------------------------------------------
    # 1. SAFETY DETECTORS
    # -------------------------------------------------------------------------
    def detect_safety_signals(self, cut: int) -> List[Finding]:
        findings: List[Finding] = []
        for usubjid, subj in self.qs.graph.subjects.items():
            first_dose_dt = self.qs.get_first_dose_date(usubjid)
            events = self.qs.get_events(usubjid)

            # Check Adverse Events
            for ae in events:
                if ae.quarantined:
                    continue

                # Rule 1: AESHOSP=Y with AESER=N (Miscoded SAE)
                if ae.hospitalisation.upper() == "Y" and ae.serious.upper() == "N":
                    findings.append(Finding(
                        finding_id=f"F-SAE-HOSP-{usubjid}-{ae.seq}",
                        code="SAE_HOSPITALISATION_MISCODED",
                        usubjid=usubjid,
                        site=subj.siteid,
                        severity="CRITICAL",
                        category="safety",
                        rationale=(
                            f"Adverse event '{ae.term}' flagged with hospitalization (AESHOSP=Y) "
                            f"but coded as non-serious (AESER=N). Per protocol §6, hospitalization mandates SAE classification."
                        ),
                        evidence=[EvidenceRef(domain="AE", usubjid=usubjid, seq=ae.seq)],
                        cut=cut,
                        protocol_version=self.protocol_version,
                        alternatives_considered=["Maintain as non-serious per investigator AESER coding"],
                    ))
                elif ae.hospitalisation.upper() == "Y" or ae.serious.upper() == "Y":
                    # Standard SAE
                    findings.append(Finding(
                        finding_id=f"F-SAE-{usubjid}-{ae.seq}",
                        code="SERIOUS_ADVERSE_EVENT",
                        usubjid=usubjid,
                        site=subj.siteid,
                        severity="CRITICAL",
                        category="safety",
                        rationale=f"Serious Adverse Event reported: '{ae.term}' (AESER={ae.serious}, AESHOSP={ae.hospitalisation}).",
                        evidence=[EvidenceRef(domain="AE", usubjid=usubjid, seq=ae.seq)],
                        cut=cut,
                        protocol_version=self.protocol_version,
                    ))

                # Rule 2: AE onset before first dose
                if first_dose_dt and ae.start_date:
                    if ae.start_date < first_dose_dt:
                        findings.append(Finding(
                            finding_id=f"F-AE-PREDOSE-{usubjid}-{ae.seq}",
                            code="AE_BEFORE_FIRST_DOSE",
                            usubjid=usubjid,
                            site=subj.siteid,
                            severity="MEDIUM",
                            category="data_quality",
                            rationale=(
                                f"AE '{ae.term}' starts on {ae.start_date} prior to first study dose on {first_dose_dt}. "
                                f"Requires verification against medical history / source documents."
                            ),
                            evidence=[EvidenceRef(domain="AE", usubjid=usubjid, seq=ae.seq)],
                            cut=cut,
                            protocol_version=self.protocol_version,
                        ))

            # Rule 3: Hy's Law Screening (ALT/AST > 3x ULN + BILI > 2x ULN within 14 days)
            hys_findings = self._check_hys_law(subj, cut)
            findings.extend(hys_findings)

        return findings

    def _check_hys_law(self, subj, cut: int) -> List[Finding]:
        findings = []
        labs = self.qs.get_labs(subj.usubjid)
        # Filter non-quarantined labs with dates and values
        valid_labs = [lb for lb in labs if not lb.quarantined and lb.date and lb.value_std is not None]

        # Standard ULNs (from central lab reference ranges: ALT=56, AST=40, BILI=1.2)
        alt_uln = 56.0
        ast_uln = 40.0
        bili_uln = 1.2

        alt_elevations = [lb for lb in valid_labs if lb.test_code == "ALT" and lb.value_std > (3.0 * alt_uln)]
        ast_elevations = [lb for lb in valid_labs if lb.test_code == "AST" and lb.value_std > (3.0 * ast_uln)]
        bili_elevations = [lb for lb in valid_labs if lb.test_code == "BILI" and lb.value_std > (2.0 * bili_uln)]

        trans_elevations = alt_elevations + ast_elevations

        for t_lb in trans_elevations:
            # Look for concurrent BILI within 14 days
            try:
                t_dt = datetime.strptime(t_lb.date, "%Y-%m-%d")
            except Exception:
                continue

            for b_lb in bili_elevations:
                try:
                    b_dt = datetime.strptime(b_lb.date, "%Y-%m-%d")
                except Exception:
                    continue

                diff_days = abs((t_dt - b_dt).days)
                if diff_days <= 14:
                    evidence = [
                        EvidenceRef(domain="LB", usubjid=subj.usubjid, seq=t_lb.seq),
                        EvidenceRef(domain="LB", usubjid=subj.usubjid, seq=b_lb.seq),
                    ]
                    findings.append(Finding(
                        finding_id=f"F-HYS-{subj.usubjid}-{t_lb.seq}-{b_lb.seq}",
                        code="HYS_LAW_CANDIDATE",
                        usubjid=subj.usubjid,
                        site=subj.siteid,
                        severity="CRITICAL",
                        category="safety",
                        rationale=(
                            f"Potential Hy's Law candidate: {t_lb.test_code}={t_lb.value_raw} {t_lb.unit_raw} "
                            f"(normalized {t_lb.value_std:.1f} U/L > 3x ULN) and BILI={b_lb.value_raw} {b_lb.unit_raw} "
                            f"(> 2x ULN) within {diff_days} days."
                        ),
                        evidence=evidence,
                        cut=cut,
                        protocol_version=self.protocol_version,
                        alternatives_considered=[
                            "Pre-existing baseline transaminase elevation without acute drug-induced liver injury",
                            "Biliary obstruction or non-hepatic jaundice source"
                        ],
                    ))
                    break  # Flag once per transaminase elevation event
        return findings

    # -------------------------------------------------------------------------
    # 2. DATA QUALITY DETECTORS
    # -------------------------------------------------------------------------
    def detect_data_quality(self, cut: int) -> List[Finding]:
        findings: List[Finding] = []
        for usubjid, subj in self.qs.graph.subjects.items():
            labs = self.qs.get_labs(usubjid)
            seen_lab_seqs = set()
            for lb in labs:
                # Check for duplicate sequence numbers within domain
                if lb.seq in seen_lab_seqs:
                    findings.append(Finding(
                        finding_id=f"F-DQ-DUP-{usubjid}-{lb.seq}",
                        code="DUPLICATE_RECORD_SEQUENCE",
                        usubjid=usubjid,
                        site=subj.siteid,
                        severity="MEDIUM",
                        category="data_quality",
                        rationale=f"Duplicate sequence number LBSEQ={lb.seq} detected for subject {usubjid}.",
                        evidence=[EvidenceRef(domain="LB", usubjid=usubjid, seq=lb.seq)],
                        cut=cut,
                        protocol_version=self.protocol_version,
                    ))
                seen_lab_seqs.add(lb.seq)

                # Check for missing/unparseable numeric values where value_raw is non-empty but unparseable
                if lb.value_raw and lb.value_num is None:
                    # Non-numeric result check
                    if lb.value_raw.strip().upper() not in ["<5", "ND", "BLANK"]:
                        findings.append(Finding(
                            finding_id=f"F-DQ-MALFORMED-{usubjid}-{lb.seq}",
                            code="DATA_MALFORMED_LAB_VALUE",
                            usubjid=usubjid,
                            site=subj.siteid,
                            severity="LOW",
                            category="data_quality",
                            rationale=f"Lab test {lb.test_code} contains non-standard text value '{lb.value_raw}'.",
                            evidence=[EvidenceRef(domain="LB", usubjid=usubjid, seq=lb.seq)],
                            cut=cut,
                            protocol_version=self.protocol_version,
                        ))

                # Unit mismatch check: check if unit_raw is reported and unknown / unexpected
                if lb.unit_raw:
                    known_units = ["U/L", "mg/dL", "%", "ukat/L", "µkat/L", "umol/L", "mmol/L"]
                    if not any(k.lower() == lb.unit_raw.strip().lower() for k in known_units):
                        findings.append(Finding(
                            finding_id=f"F-DQ-UNIT-MISMATCH-{usubjid}-{lb.seq}",
                            code="LAB_UNIT_MISMATCH",
                            usubjid=usubjid,
                            site=subj.siteid,
                            severity="LOW",
                            category="data_quality",
                            rationale=f"Lab test {lb.test_code} reports unmapped unit '{lb.unit_raw}'.",
                            evidence=[EvidenceRef(domain="LB", usubjid=usubjid, seq=lb.seq)],
                            cut=cut,
                            protocol_version=self.protocol_version,
                        ))

            # Exposure check: Verify missing doses for active randomized subjects
            doses = self.qs.get_doses(usubjid)
            if len(doses) == 0 and subj.rfstdtc:
                findings.append(Finding(
                    finding_id=f"F-DQ-MISSING-DOSE-{usubjid}",
                    code="MISSING_DOSE_RECORD",
                    usubjid=usubjid,
                    site=subj.siteid,
                    severity="MEDIUM",
                    category="data_quality",
                    rationale=f"Subject randomized with first dose date {subj.rfstdtc} but has 0 exposure records in EX domain.",
                    evidence=[EvidenceRef(domain="DM", usubjid=usubjid, seq=1)],
                    cut=cut,
                    protocol_version=self.protocol_version,
                ))

        return findings

    # -------------------------------------------------------------------------
    # 3. COMPLIANCE DETECTORS
    # -------------------------------------------------------------------------
    def detect_compliance_deviations(self, cut: int) -> List[Finding]:
        findings: List[Finding] = []
        incl_rules = self.rules.get("inclusion", {})
        excl_rules = self.rules.get("exclusion", {})
        prohibited_classes = self.rules.get("prohibited_med_classes", [])
        window_days = self.rules.get("visit_window_days", 7)

        for usubjid, subj in self.qs.graph.subjects.items():
            # 1. Inclusion Criteria: Age
            if subj.age is not None:
                if subj.age < incl_rules.get("age_min", 18) or subj.age > incl_rules.get("age_max", 75):
                    findings.append(Finding(
                        finding_id=f"F-COMPL-AGE-{usubjid}",
                        code="ELIGIBILITY_AGE_VIOLATION",
                        usubjid=usubjid,
                        site=subj.siteid,
                        severity="HIGH",
                        category="compliance",
                        rationale=f"Subject age {subj.age} outside inclusion criteria [18-75].",
                        evidence=[EvidenceRef(domain="DM", usubjid=usubjid, seq=1)],
                        cut=cut,
                        protocol_version=self.protocol_version,
                    ))

            # 2. Inclusion Criteria: Screening HbA1c
            if subj.scr_hba1c is not None:
                if subj.scr_hba1c < incl_rules.get("hba1c_min", 7.0) or subj.scr_hba1c > incl_rules.get("hba1c_max", 10.5):
                    findings.append(Finding(
                        finding_id=f"F-COMPL-HBA1C-{usubjid}",
                        code="ELIGIBILITY_HBA1C_VIOLATION",
                        usubjid=usubjid,
                        site=subj.siteid,
                        severity="HIGH",
                        category="compliance",
                        rationale=f"Screening HbA1c {subj.scr_hba1c}% outside inclusion range [7.0% - 10.5%].",
                        evidence=[EvidenceRef(domain="DM", usubjid=usubjid, seq=1)],
                        cut=cut,
                        protocol_version=self.protocol_version,
                    ))

            # 3. Exclusion Criteria: Screening Hepatic (ALT or AST > 2x ULN at screening)
            scr_labs = self.qs.get_screening_labs(usubjid)
            alt_uln = 56.0
            ast_uln = 40.0
            if "ALT" in scr_labs and scr_labs["ALT"].value_std:
                if scr_labs["ALT"].value_std > (2.0 * alt_uln):
                    findings.append(Finding(
                        finding_id=f"F-COMPL-EXCL-ALT-{usubjid}",
                        code="EXCLUSION_HEPATIC_VIOLATION",
                        usubjid=usubjid,
                        site=subj.siteid,
                        severity="HIGH",
                        category="compliance",
                        rationale=f"Screening ALT {scr_labs['ALT'].value_std:.1f} U/L > 2x ULN ({2.0*alt_uln:.1f} U/L). Known hepatic exclusion violation.",
                        evidence=[EvidenceRef(domain="LB", usubjid=usubjid, seq=scr_labs["ALT"].seq)],
                        cut=cut,
                        protocol_version=self.protocol_version,
                    ))

            # 4. Exclusion Criteria: Screening Creatinine > 1.5 mg/dL (Added in Protocol v2/v3)
            creat_max = excl_rules.get("creatinine_max")
            if creat_max is not None and "CREAT" in scr_labs and scr_labs["CREAT"].value_num:
                if scr_labs["CREAT"].value_num > creat_max:
                    findings.append(Finding(
                        finding_id=f"F-COMPL-EXCL-CREAT-{usubjid}",
                        code="EXCLUSION_RENAL_VIOLATION",
                        usubjid=usubjid,
                        site=subj.siteid,
                        severity="HIGH",
                        category="compliance",
                        rationale=f"Screening Creatinine {scr_labs['CREAT'].value_num} mg/dL > {creat_max} mg/dL limit in Protocol v{self.protocol_version}.",
                        evidence=[EvidenceRef(domain="LB", usubjid=usubjid, seq=scr_labs["CREAT"].seq)],
                        cut=cut,
                        protocol_version=self.protocol_version,
                    ))

            # 5. Prohibited Concomitant Medications
            meds = self.qs.get_medications(usubjid)
            for med in meds:
                if med.class_name and any(p.lower() in med.class_name.lower() for p in prohibited_classes):
                    findings.append(Finding(
                        finding_id=f"F-COMPL-PROHIB-MED-{usubjid}-{med.seq}",
                        code=f"PROHIBITED_MEDICATION_{med.class_name.upper().replace(' ', '_')}",
                        usubjid=usubjid,
                        site=subj.siteid,
                        severity="HIGH",
                        category="compliance",
                        rationale=f"Prohibited concomitant medication class '{med.class_name}' ({med.name}) under Protocol v{self.protocol_version}.",
                        evidence=[EvidenceRef(domain="CM", usubjid=usubjid, seq=med.seq)],
                        cut=cut,
                        protocol_version=self.protocol_version,
                    ))

            # 6. Dosing Error
            doses = self.qs.get_doses(usubjid)
            for d in doses:
                expected_dose = 10.0 if (subj.arm and "DRUG" in subj.arm.upper()) else 0.0
                if d.dose is not None and d.dose != expected_dose:
                    findings.append(Finding(
                        finding_id=f"F-COMPL-DOSE-{usubjid}-{d.seq}",
                        code="DOSING_ERROR_DEVIATION",
                        usubjid=usubjid,
                        site=subj.siteid,
                        severity="HIGH",
                        category="compliance",
                        rationale=f"Administered dose {d.dose} {d.dose_unit} differs from expected {expected_dose} mg for arm {subj.arm}.",
                        evidence=[EvidenceRef(domain="EX", usubjid=usubjid, seq=d.seq)],
                        cut=cut,
                        protocol_version=self.protocol_version,
                    ))

            # 7. Visit Window Deviations
            vitals = self.qs.get_vitals(usubjid)
            if subj.rfstdtc:
                try:
                    baseline_dt = datetime.strptime(subj.rfstdtc, "%Y-%m-%d")
                    for vs in vitals:
                        if not vs.visit or not vs.date:
                            continue
                        visit_clean = vs.visit.strip().upper()
                        if visit_clean in self.SCHEDULED_VISIT_DAYS:
                            sched_day = self.SCHEDULED_VISIT_DAYS[visit_clean]
                            actual_dt = datetime.strptime(vs.date, "%Y-%m-%d")
                            actual_day = (actual_dt - baseline_dt).days
                            day_delta = abs(actual_day - sched_day)
                            if day_delta > window_days:
                                findings.append(Finding(
                                    finding_id=f"F-COMPL-WINDOW-{usubjid}-{vs.seq}",
                                    code="VISIT_WINDOW_DEVIATION",
                                    usubjid=usubjid,
                                    site=subj.siteid,
                                    severity="LOW",
                                    category="compliance",
                                    rationale=(
                                        f"Visit '{vs.visit}' occurred on Day {actual_day} (delta {day_delta} days from scheduled Day {sched_day}), "
                                        f"exceeding the +/- {window_days} days window under Protocol v{self.protocol_version}."
                                    ),
                                    evidence=[EvidenceRef(domain="VS", usubjid=usubjid, seq=vs.seq)],
                                    cut=cut,
                                    protocol_version=self.protocol_version,
                                ))
                except Exception:
                    pass

        return findings

    # -------------------------------------------------------------------------
    # 4. SITE-LEVEL RECURRING PATTERNS
    # -------------------------------------------------------------------------
    def detect_site_level_patterns(self, cut: int) -> List[Finding]:
        findings: List[Finding] = []
        for site_id, subj_ids in self.qs.graph.sites.items():
            site_subjs = [self.qs.graph.subjects[s] for s in subj_ids if s in self.qs.graph.subjects]
            if not site_subjs:
                continue

            # Check recurring prohibited meds or protocol deviations at site level
            prohib_count = 0
            ev_list = []
            for s in site_subjs:
                meds = self.qs.get_medications(s.usubjid)
                for m in meds:
                    if m.class_name and any(p.lower() in m.class_name.lower() for p in self.rules.get("prohibited_med_classes", [])):
                        prohib_count += 1
                        ev_list.append(EvidenceRef(domain="CM", usubjid=s.usubjid, seq=m.seq))

            if prohib_count >= 3:
                findings.append(Finding(
                    finding_id=f"F-SITE-RECURRING-PROHIB-{site_id}",
                    code="SITE_RECURRING_COMPLIANCE_ISSUE",
                    usubjid=site_subjs[0].usubjid,
                    site=site_id,
                    severity="HIGH",
                    category="site",
                    rationale=f"Site {site_id} exhibits {prohib_count} recurring prohibited medication deviations across multiple subjects.",
                    evidence=ev_list[:5],
                    cut=cut,
                    protocol_version=self.protocol_version,
                ))

        return findings
