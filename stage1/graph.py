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
