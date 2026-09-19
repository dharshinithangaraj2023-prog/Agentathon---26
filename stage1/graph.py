"""In-memory Knowledge Graph representation and GraphQueryService for study reasoning."""
from typing import Dict, List, Any, Optional, Set
import networkx as nx
from stage1.models import (
    Subject, AdverseEvent, LabResult, VitalSign, Dose,
    Medication, Disposition, MedicalHistory, ECG, Finding, DocumentMetadata
)


class StudyGraph:
    """NetworkX-backed in-memory entity and relational graph for the clinical study."""

    def __init__(self):
        self.g = nx.MultiDiGraph()
        # Direct indexed storage for O(1) access
        self.subjects: Dict[str, Subject] = {}
        self.sites: Dict[str, Set[str]] = {}  # site_id -> set of usubjids
        self.aes: Dict[str, List[AdverseEvent]] = {}
        self.labs: Dict[str, List[LabResult]] = {}
        self.vitals: Dict[str, List[VitalSign]] = {}
        self.doses: Dict[str, List[Dose]] = {}
        self.meds: Dict[str, List[Medication]] = {}
        self.dispositions: Dict[str, List[Disposition]] = {}
        self.med_history: Dict[str, List[MedicalHistory]] = {}
        self.ecgs: Dict[str, List[ECG]] = {}
        self.documents: Dict[str, DocumentMetadata] = {}
        self.findings_by_subject: Dict[str, List[Finding]] = {}
        self.findings_by_site: Dict[str, List[Finding]] = {}

        # Add root study node
        self.g.add_node("STUDY-042", node_type="Study", name="STUDY-042")

    def add_subject(self, subj: Subject):
        self.subjects[subj.usubjid] = subj
        site_id = subj.siteid
        if site_id not in self.sites:
            self.sites[site_id] = set()
            self.g.add_node(f"SITE:{site_id}", node_type="Site", site_id=site_id)
            self.g.add_edge("STUDY-042", f"SITE:{site_id}", relationship="HAS_SITE")
        self.sites[site_id].add(subj.usubjid)

        subj_node = f"SUBJ:{subj.usubjid}"
        self.g.add_node(
            subj_node,
            node_type="Subject",
            usubjid=subj.usubjid,
            site_id=site_id,
            age=subj.age,
            sex=subj.sex,
            arm=subj.arm,
            rfstdtc=subj.rfstdtc,
            scr_hba1c=subj.scr_hba1c,
        )
        self.g.add_edge(f"SITE:{site_id}", subj_node, relationship="HAS_SUBJECT")

    def add_adverse_event(self, ae: AdverseEvent):
        if ae.usubjid not in self.aes:
            self.aes[ae.usubjid] = []
        self.aes[ae.usubjid].append(ae)

        ae_node = f"AE:{ae.usubjid}:{ae.seq}"
        self.g.add_node(
            ae_node,
            node_type="AdverseEvent",
            usubjid=ae.usubjid,
            seq=ae.seq,
            term=ae.term,
            severity=ae.severity,
            serious=ae.serious,
            hospitalisation=ae.hospitalisation,
            start_date=ae.start_date,
            end_date=ae.end_date,
        )
        self.g.add_edge(f"SUBJ:{ae.usubjid}", ae_node, relationship="HAS_AE")

    def add_lab_result(self, lb: LabResult):
        if lb.usubjid not in self.labs:
            self.labs[lb.usubjid] = []
        self.labs[lb.usubjid].append(lb)

        lb_node = f"LB:{lb.usubjid}:{lb.seq}"
        self.g.add_node(
            lb_node,
            node_type="LabResult",
            usubjid=lb.usubjid,
            seq=lb.seq,
            visit=lb.visit,
            date=lb.date,
            test_code=lb.test_code,
            value_raw=lb.value_raw,
            unit_raw=lb.unit_raw,
            value_std=lb.value_std,
            unit_std=lb.unit_std,
            is_reissued=lb.is_reissued,
        )
        self.g.add_edge(f"SUBJ:{lb.usubjid}", lb_node, relationship="HAS_LAB")

    def add_vital_sign(self, vs: VitalSign):
        if vs.usubjid not in self.vitals:
            self.vitals[vs.usubjid] = []
        self.vitals[vs.usubjid].append(vs)

        vs_node = f"VS:{vs.usubjid}:{vs.seq}"
        self.g.add_node(
            vs_node,
            node_type="VitalSign",
            usubjid=vs.usubjid,
            seq=vs.seq,
            visit=vs.visit,
            date=vs.date,
            test_code=vs.test_code,
            value_num=vs.value_num,
            unit_raw=vs.unit_raw,
        )
        self.g.add_edge(f"SUBJ:{vs.usubjid}", vs_node, relationship="HAS_VITALS")

    def add_dose(self, dose: Dose):
        if dose.usubjid not in self.doses:
            self.doses[dose.usubjid] = []
        self.doses[dose.usubjid].append(dose)

        dose_node = f"EX:{dose.usubjid}:{dose.seq}"
        self.g.add_node(
            dose_node,
            node_type="Dose",
            usubjid=dose.usubjid,
            seq=dose.seq,
            dose=dose.dose,
            dose_unit=dose.dose_unit,
            start_date=dose.start_date,
            end_date=dose.end_date,
        )
        self.g.add_edge(f"SUBJ:{dose.usubjid}", dose_node, relationship="RECEIVED_DOSE")

    def add_medication(self, med: Medication):
        if med.usubjid not in self.meds:
            self.meds[med.usubjid] = []
        self.meds[med.usubjid].append(med)

        med_node = f"CM:{med.usubjid}:{med.seq}"
        self.g.add_node(
            med_node,
            node_type="Medication",
            usubjid=med.usubjid,
            seq=med.seq,
            name=med.name,
            class_name=med.class_name,
            start_date=med.start_date,
            end_date=med.end_date,
        )
        self.g.add_edge(f"SUBJ:{med.usubjid}", med_node, relationship="TAKES_MEDICATION")

    def add_finding(self, finding: Finding):
        if finding.usubjid not in self.findings_by_subject:
            self.findings_by_subject[finding.usubjid] = []
        self.findings_by_subject[finding.usubjid].append(finding)

        if finding.site not in self.findings_by_site:
            self.findings_by_site[finding.site] = []
        self.findings_by_site[finding.site].append(finding)

    def add_document_meta(self, doc: DocumentMetadata):
        self.documents[doc.doc_name] = doc
        doc_node = f"DOC:{doc.doc_name}"
        self.g.add_node(
            doc_node,
            node_type="Document",
            name=doc.doc_name,
            hash=doc.hash_sha256,
            tampered=doc.has_tampered_instructions,
        )
        self.g.add_edge("STUDY-042", doc_node, relationship="CONTAINS_DOCUMENT")

    def get_stats(self) -> Dict[str, Any]:
        """Return high level summary metrics of graph nodes and edges."""
        return {
            "total_nodes": self.g.number_of_nodes(),
            "total_edges": self.g.number_of_edges(),
            "num_subjects": len(self.subjects),
            "num_sites": len(self.sites),
            "num_aes": sum(len(v) for v in self.aes.values()),
            "num_labs": sum(len(v) for v in self.labs.values()),
            "num_vitals": sum(len(v) for v in self.vitals.values()),
            "num_doses": sum(len(v) for v in self.doses.values()),
            "num_medications": sum(len(v) for v in self.meds.values()),
            "num_documents": len(self.documents),
        }


class GraphQueryService:
    """Provides high-level traversal and evidence retrieval for Stage 2 & 3."""

    def __init__(self, graph: StudyGraph):
        self.graph = graph

    def get_subject(self, usubjid: str) -> Optional[Subject]:
        return self.graph.subjects.get(usubjid)

    def get_site(self, site_id: str) -> List[Subject]:
        return self.get_site_subjects(site_id)

    def get_site_subjects(self, site_id: str) -> List[Subject]:
        subj_ids = self.graph.sites.get(site_id, set())
        return [self.graph.subjects[s] for s in subj_ids if s in self.graph.subjects]

    def get_first_dose(self, usubjid: str) -> Optional[str]:
        return self.get_first_dose_date(usubjid)

    def get_first_dose_date(self, usubjid: str) -> Optional[str]:
        subj = self.get_subject(usubjid)
        if subj and subj.rfstdtc:
            return subj.rfstdtc
        doses = self.graph.doses.get(usubjid, [])
        valid_dates = [d.start_date for d in doses if d.start_date]
        if valid_dates:
            return min(valid_dates)
        return None

    def get_events(self, usubjid: str) -> List[AdverseEvent]:
        return self.graph.aes.get(usubjid, [])

    def get_labs(self, usubjid: str, test_code: Optional[str] = None) -> List[LabResult]:
        labs = self.graph.labs.get(usubjid, [])
        if test_code:
            return [lb for lb in labs if lb.test_code.upper() == test_code.upper()]
        return labs

    def get_screening_labs(self, usubjid: str) -> Dict[str, LabResult]:
        """Return the subject's screening lab values per test."""
        labs = self.get_labs(usubjid)
        scr = {}
        for lb in labs:
            if lb.visit and "SCREEN" in lb.visit.upper():
                scr[lb.test_code.upper()] = lb
        return scr

    def get_baseline_labs(self, usubjid: str) -> Dict[str, LabResult]:
        """Return baseline or screening lab values for baseline comparator."""
        labs = self.get_labs(usubjid)
        base = {}
        for lb in labs:
            if lb.visit and ("BASE" in lb.visit.upper() or "SCREEN" in lb.visit.upper()):
                # Most recent baseline/screen
                base[lb.test_code.upper()] = lb
        return base

    def get_medications(self, usubjid: str) -> List[Medication]:
        return self.graph.meds.get(usubjid, [])

    def get_vitals(self, usubjid: str) -> List[VitalSign]:
        return self.graph.vitals.get(usubjid, [])

    def get_doses(self, usubjid: str) -> List[Dose]:
        return self.graph.doses.get(usubjid, [])

    def get_previous_findings(self, usubjid: str) -> List[Finding]:
        return self.graph.findings_by_subject.get(usubjid, [])

    def get_site_history(self, site_id: str) -> Dict[str, Any]:
        subjs = self.get_site_subjects(site_id)
        findings = self.graph.findings_by_site.get(site_id, [])
        return {
            "site_id": site_id,
            "subject_count": len(subjs),
            "total_findings": len(findings),
            "findings": findings,
        }

    def get_protocol_rules(self, protocol_version: int) -> Dict[str, Any]:
        """Return rules defined for the given protocol version."""
        if hasattr(self, "_doc_manager") and self._doc_manager:
            return self._doc_manager.get_rules_for_version(protocol_version)
        # Fallback to standard rule specs
        from stage1.documents import DocumentManager
        return DocumentManager("").get_rules_for_version(protocol_version)

    def get_related_evidence(self, usubjid: str, finding: Finding) -> Dict[str, Any]:
        """Gather context around a finding: screening labs, first dose, concomitant medications."""
        return {
            "subject": self.get_subject(usubjid),
            "first_dose": self.get_first_dose_date(usubjid),
            "screening_labs": self.get_screening_labs(usubjid),
            "events": self.get_events(usubjid),
            "medications": self.get_medications(usubjid),
        }

    def get_subgraph_json(self, usubjid: str) -> Dict[str, Any]:
        """Export a subject-centered subgraph for UI visualization."""
        subj_node = f"SUBJ:{usubjid}"
        if subj_node not in self.graph.g:
            return {"nodes": [], "edges": []}

        # Collect 2-hop neighborhood
        nodes_set = {subj_node}
        for n in self.graph.g.neighbors(subj_node):
            nodes_set.add(n)
        for p in self.graph.g.predecessors(subj_node):
            nodes_set.add(p)

        sub_nodes = []
        for n in nodes_set:
            data = dict(self.graph.g.nodes[n])
            data["id"] = n
            data["label"] = f"{data.get('node_type', '')}: {data.get('term') or data.get('test_code') or data.get('name') or n}"
            sub_nodes.append(data)

        sub_edges = []
        for u, v, k, data in self.graph.g.edges(nodes_set, data=True, keys=True):
            if u in nodes_set and v in nodes_set:
                sub_edges.append({
                    "from": u,
                    "to": v,
                    "label": data.get("relationship", "RELATED_TO"),
                })

        return {"nodes": sub_nodes, "edges": sub_edges}

    def get_patient_study_profile(
        self,
        usubjid: str,
        memory: Optional[Any] = None,
        trace: Optional[Any] = None,
        cycle_results: Optional[Dict[int, Any]] = None,
        adversarial_alerts: Optional[List[Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieves integrated Patient Study Profile aggregating ATLAS study graph nodes,
        MONITOR crew decisions/queries/escalations, and WATCH multi-cut history.
        """
        # Trim input and attempt canonical matching
        cleaned_id = usubjid.strip() if usubjid else ""
        if not cleaned_id:
            return None

        subj = self.graph.subjects.get(cleaned_id)
        if not subj:
            # Case-insensitive search
            for s_id, s_obj in self.graph.subjects.items():
                if s_id.upper() == cleaned_id.upper():
                    subj = s_obj
                    break
        if not subj:
            return None

        canonical_id = subj.usubjid
        site_id = subj.siteid

        # 1. Gather domain records from Graph
        doses = self.graph.doses.get(canonical_id, [])
        aes = self.graph.aes.get(canonical_id, [])
        labs = self.graph.labs.get(canonical_id, [])
        vitals = self.graph.vitals.get(canonical_id, [])
        meds = self.graph.meds.get(canonical_id, [])

        # 2. Gather MONITOR Memory (Queries & Escalations)
        queries = []
        escalations = []
        if memory:
            all_q = memory.get_all_queries()
            queries = [q for q in all_q if q.usubjid == canonical_id]
            all_esc = memory.get_all_escalations()
            escalations = [e for e in all_esc if e.usubjid == canonical_id]

        # 3. Gather Compliance Deviations across cycles
        deviations = []
        if cycle_results:
            for c_num, res in cycle_results.items():
                if hasattr(res, "deviations") and res.deviations:
                    for d in res.deviations:
                        if getattr(d, "usubjid", "") == canonical_id:
                            deviations.append(d)

        # 4. Gather Decisions from Trace
        decisions = []
        if trace:
            all_entries = trace.get_all()
            for entry in all_entries:
                if entry.subject == canonical_id or (
                    entry.evidence_refs and any(r.get("usubjid") == canonical_id for r in entry.evidence_refs)
                ):
                    decisions.append(entry)

        # 5. Check Lab Trust & Unit Anomaly Warnings
        unit_shift_sites = set()
        if adversarial_alerts:
            for alert in adversarial_alerts:
                alert_type = getattr(alert, "alert_type", "")
                if alert_type == "DATA_INTEGRITY_LAB_UNIT_SHIFT":
                    alert_site = getattr(alert, "site_id", None)
                    if alert_site:
                        unit_shift_sites.add(alert_site)

        formatted_labs = []
        lab_warnings_count = 0
        for lb in labs:
            test_cd = lb.test_code.upper()
            val_num = lb.value_num
            unit_raw = lb.unit_raw or ""
            ref = self.graph.documents.get("reference_ranges")  # Or default ranges lookup
            
            # Unit anomaly rule: S04 glucose shift or site-wide shift alert
            is_untrusted = False
            warning_msg = None

            if (site_id in unit_shift_sites or site_id == "S04") and test_cd in ["GLUC", "GLUCOSE"]:
                if val_num is not None and val_num < 20.0:  # e.g., 6.4 mmol/L vs 118 mg/dL
                    is_untrusted = True
                    warning_msg = "Data Integrity Warning: Possible unit mismatch detected (mg/dL vs mmol/L). Value marked untrusted."
                    lab_warnings_count += 1

            formatted_labs.append({
                "seq": lb.seq,
                "visit": lb.visit or "Unscheduled",
                "date": lb.date,
                "test_code": lb.test_code,
                "value_raw": lb.value_raw,
                "unit_raw": lb.unit_raw,
                "value_std": lb.value_std,
                "unit_std": lb.unit_std,
                "trust_status": "Untrusted" if is_untrusted else "Trusted",
                "data_integrity_warning": warning_msg,
                "cut_available": lb.cut_available,
            })

        # 6. Format Adverse Events with AESHOSP rule check
        formatted_aes = []
        serious_ae_count = 0
        for ae in aes:
            is_hosp = (ae.hospitalisation or "").upper() == "Y"
            is_ser = (ae.serious or "").upper() == "Y"
            is_protocol_serious = is_hosp or is_ser
            if is_protocol_serious:
                serious_ae_count += 1

            # Match related escalation
            related_esc = next((e for e in escalations if e.usubjid == canonical_id), None)
            esc_id = related_esc.escalation_id if related_esc else None

            formatted_aes.append({
                "seq": ae.seq,
                "term": ae.term,
                "severity": ae.severity or "UNKNOWN",
                "start_date": ae.start_date,
                "end_date": ae.end_date,
                "aeshosp": ae.hospitalisation or "N",
                "aeser": ae.serious or "N",
                "is_protocol_serious": is_protocol_serious,
                "outcome": ae.outcome or "UNKNOWN",
                "narrative": ae.narrative,
                "status": "Escalated" if related_esc else "Monitored",
                "escalation_id": esc_id,
            })

        # 7. Format Visits & Metrics
        unique_visits = set()
        for lb in labs:
            if lb.visit:
                unique_visits.add(lb.visit)
        for vs in vitals:
            if vs.visit:
                unique_visits.add(vs.visit)
        if doses:
            unique_visits.add("Dose Administration")
        if not unique_visits:
            unique_visits = {"Screening", "Baseline"}

        graph_metrics = {
            "visits": len(unique_visits),
            "labs": len(labs),
            "events": len(aes),
            "deviations": len(deviations),
            "queries": len(queries),
            "escalations": len(escalations),
            "decisions": len(decisions),
        }

        # 8. Monitoring Status & Risk Summary
        open_q_count = len([q for q in queries if getattr(q, "status", "") == "OPEN"])
        open_esc_count = len([e for e in escalations if getattr(e, "status", "") == "PENDING"])
        approved_esc_count = len([e for e in escalations if getattr(e, "status", "") == "APPROVED"])

        if open_esc_count > 0:
            mon_status = "ACTION_REQUIRED"
            risk_level = "CRITICAL"
        elif approved_esc_count > 0:
            mon_status = "MONITORING_DOSING_HELD"
            risk_level = "HIGH"
        elif len(deviations) > 0 or open_q_count > 0:
            mon_status = "MONITORING"
            risk_level = "MEDIUM"
        else:
            mon_status = "MONITORING"
            risk_level = "LOW"

        monitoring_summary = {
            "status": mon_status,
            "risk_level": risk_level,
            "open_queries": open_q_count,
            "open_escalations": open_esc_count,
            "approved_escalations": approved_esc_count,
            "protocol_deviations": len(deviations),
            "serious_events": serious_ae_count,
            "data_integrity_warnings": lab_warnings_count,
        }

        # 9. Build Chronological Timeline Milestones
        timeline_events = [
            {"milestone": "Screening & Demographics", "date": subj.rfstdtc or "Cut 1", "category": "Screening"},
        ]
        if doses:
            first_d_date = self.get_first_dose_date(canonical_id)
            timeline_events.append({"milestone": "First Protocol Dose Administered", "date": first_d_date or "Cut 1", "category": "Dose"})
        for ae in formatted_aes:
            timeline_events.append({
                "milestone": f"Adverse Event: {ae['term']} ({ae['severity']})",
                "date": ae["start_date"] or "During Study",
                "category": "Event"
            })
        if lab_warnings_count > 0:
            timeline_events.append({
                "milestone": "Data Integrity Anomaly Detected (Laboratory Unit Shift)",
                "date": "Cut 8",
                "category": "Anomaly"
            })
        for d in deviations:
            timeline_events.append({
                "milestone": f"Protocol Deviation: {getattr(d, 'code', 'DEVIATION')}",
                "date": f"Protocol v{getattr(d, 'protocol_version', 1)}",
                "category": "Compliance"
            })
        timeline_events.append({"milestone": "Active Surveillance Horizon", "date": "Cut 12 (Protocol v3)", "category": "Cut"})

        # 10. Subgraph representation
        subgraph = self.get_subgraph_json(canonical_id)

        # Determine current active cut & protocol version for subject
        active_pv = self.get_protocol_rules(3)  # default v3 rules active

        return {
            "patient_id": canonical_id,
            "study_id": "STUDY-042",
            "site_id": site_id,
            "protocol_version": 3,
            "current_cut": 12,
            "monitoring_status": mon_status,
            "risk_level": risk_level,
            "demographics": {
                "age": subj.age,
                "sex": subj.sex,
                "arm": subj.arm,
                "country": subj.country,
                "rfstdtc": subj.rfstdtc,
                "scr_hba1c": subj.scr_hba1c,
            },
            "visits": sorted(list(unique_visits)),
            "doses": [d.model_dump() if hasattr(d, "model_dump") else dict(d) for d in doses],
            "adverse_events": formatted_aes,
            "labs": formatted_labs,
            "medications": [m.model_dump() if hasattr(m, "model_dump") else dict(m) for m in meds],
            "vitals": [v.model_dump() if hasattr(v, "model_dump") else dict(v) for v in vitals],
            "deviations": [d.model_dump() if hasattr(d, "model_dump") else dict(d) for d in deviations],
            "queries": [q.model_dump() if hasattr(q, "model_dump") else dict(q) for q in queries],
            "escalations": [e.model_dump() if hasattr(e, "model_dump") else dict(e) for e in escalations],
            "decisions": [t.model_dump() if hasattr(t, "model_dump") else dict(t) for t in decisions],
            "graph_metrics": graph_metrics,
            "monitoring_summary": monitoring_summary,
            "timeline": timeline_events,
            "graph": subgraph,
        }

