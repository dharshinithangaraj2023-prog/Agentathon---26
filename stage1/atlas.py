"""Stage 1 - ATLAS main entry point for graph construction and study finding detection."""
from typing import Dict, List, Any, Optional
from stage1.models import Finding
from stage1.data_loader import DataLoader
from stage1.documents import DocumentManager
from stage1.graph import StudyGraph, GraphQueryService
from stage1.detectors import DetectorEngine
from stage1.trace import DecisionTrace


class Atlas:
    """Graph-based study/data analysis agent."""

    def __init__(self, data_dir: str, hub_url: Optional[str] = None, gateway_url: Optional[str] = None, trace: Optional[DecisionTrace] = None):
        self.data_dir = data_dir
        self.hub_url = hub_url
        self.gateway_url = gateway_url
        self.trace = trace or DecisionTrace()

        self.data_loader = DataLoader(data_dir)
        self.doc_manager = DocumentManager(data_dir)
        self.graph = StudyGraph()
        self.query_service = GraphQueryService(self.graph)
        self.current_cut: int = 1
        self.current_protocol_version: int = 1

    def build(self, cut: Optional[int] = None, protocol_version: Optional[int] = None) -> StudyGraph:
        """
        Ingests study data up to the requested cut, parses documents,
        and constructs the full in-memory relational graph.
        """
        self.current_cut = cut if cut is not None else 1
        if protocol_version is not None:
            self.current_protocol_version = protocol_version
        else:
            self.current_protocol_version = self.data_loader.get_protocol_version_for_cut(self.current_cut)

        # 1. Inspect documents & hashes
        doc_metas = self.doc_manager.inspect_documents()
        self.graph = StudyGraph()
        for doc in doc_metas:
            self.graph.add_document_meta(doc)
            if doc.has_tampered_instructions:
                self.trace.record(
                    cut=self.current_cut,
                    protocol_version=self.current_protocol_version,
                    node="detect",
                    decision_id=f"DEC-TAMPER-{doc.doc_name}",
                    action="AUTOMATED_INSTRUCTION_IGNORED",
                    reason=f"Document {doc.doc_name} contained prompt injection directives. Ignored as passive data.",
                    details={"ignored_instructions": doc.ignored_instructions},
                )

        # 2. Load domain datasets up to cut
        domains = self.data_loader.load_all_domains(cut=self.current_cut, apply_corrections=True)

        # 3. Populate Graph
        for subj in domains.get("DM", []):
            self.graph.add_subject(subj)
        for ae in domains.get("AE", []):
            self.graph.add_adverse_event(ae)
        for lb in domains.get("LB", []):
            self.graph.add_lab_result(lb)
        for vs in domains.get("VS", []):
            self.graph.add_vital_sign(vs)
        for ex in domains.get("EX", []):
            self.graph.add_dose(ex)
        for cm in domains.get("CM", []):
            self.graph.add_medication(cm)

        self.query_service = GraphQueryService(self.graph)
        return self.graph

    def run(self, cut: int, protocol_version: Optional[int] = None) -> List[Finding]:
        """
        Execute finding detection on the graph for the given cut and protocol version.
        """
        self.build(cut=cut, protocol_version=protocol_version)
        rules = self.doc_manager.get_rules_for_version(self.current_protocol_version)

        detector = DetectorEngine(
            query_service=self.query_service,
            reference_ranges=self.data_loader.reference_ranges,
            rules=rules,
        )
        findings = detector.run_all(cut=cut)

        # Register findings back to graph
        for f in findings:
            self.graph.add_finding(f)

        # Record detect node trace
        self.trace.record(
            cut=cut,
            protocol_version=self.current_protocol_version,
            node="detect",
            decision_id=f"DEC-DETECT-CUT{cut}",
            action="FINDINGS_DETECTED",
            reason=f"Detected {len(findings)} raw findings under Protocol v{self.current_protocol_version}.",
            details={
                "total_findings": len(findings),
                "safety": len([f for f in findings if f.category == "safety"]),
                "data_quality": len([f for f in findings if f.category == "data_quality"]),
                "compliance": len([f for f in findings if f.category == "compliance"]),
                "site": len([f for f in findings if f.category == "site"]),
            },
        )

        return findings

    def graph_stats(self) -> Dict[str, Any]:
        """Return graph node and edge statistics."""
        return self.graph.get_stats()
