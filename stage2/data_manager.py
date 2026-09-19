"""Stage 2 Node 3: Data Manager - Generates actionable queries and processes site responses."""
import os
import json
from typing import List, Dict, Any, Optional
from stage1.models import Finding
from stage1.graph import GraphQueryService
from stage1.trace import DecisionTrace
from stage2.models import Query
from stage2.memory import CrewMemory


class DataManagerNode:
    """Manages data-quality issues, query generation, deduplication, and site query resolution."""

    def __init__(self, data_dir: str, query_service: GraphQueryService, memory: CrewMemory, trace: DecisionTrace):
        self.qs = query_service
        self.memory = memory
        self.trace = trace
        self.site_replies = self._load_site_replies(data_dir)

    def _resolve_responses_dir(self, base_path: str) -> str:
        candidates = [
            os.path.join(base_path, "responses"),
            os.path.join(base_path, "hackathon-data", "responses"),
            os.path.join(base_path, "hackathon-data", "hackathon-data", "responses"),
            base_path,
        ]
        for p in candidates:
            if os.path.exists(os.path.join(p, "site_replies.json")):
                return p
        return base_path

    def _load_site_replies(self, data_dir: str) -> Dict[str, Any]:
        resp_dir = self._resolve_responses_dir(data_dir)
        path = os.path.join(resp_dir, "site_replies.json")
        if not os.path.exists(path):
            return {"_default": ["ANSWERED", "Data verified against source documents. No change."], "replies": {}}
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"_default": ["ANSWERED", "Data verified against source documents. No change."], "replies": {}}

    def process_findings(self, findings: List[Finding], cut: int, protocol_version: int) -> List[Query]:
        """
        Convert data-quality findings into actionable, non-duplicate queries.
        """
        queries: List[Query] = []
        dq_findings = [f for f in findings if f.category == "data_quality"]

        for f in dq_findings:
            if not f.evidence:
                continue

            ev = f.evidence[0]
            actionable_text = self._build_query_text(f, ev)

            query = Query(
                cut=cut,
                domain=ev.domain,
                usubjid=ev.usubjid,
                seq=ev.seq,
                issue_code=f.code,
                text=actionable_text,
                status="OPEN",
            )
            query.compute_fingerprint()

            # Deduplication Check
            if self.memory.is_query_duplicate(query):
                self.trace.record(
                    cut=cut,
                    protocol_version=protocol_version,
                    node="data_manager",
                    decision_id=f"DEC-DM-DEDUP-{query.domain}-{query.usubjid}-{query.seq}",
                    action="SUPPRESS_DUPLICATE_QUERY",
                    finding_id=f.finding_id,
                    subject=query.usubjid,
                    site=f.site,
                    reason=f"Query suppressed: Duplicate query already active or answered for record ({query.domain}, {query.usubjid}, {query.seq}).",
                    evidence_refs=[ev.model_dump()],
                )
                continue

            # Query the mock site replies gateway
            lookup_key = f"{query.domain}|{query.usubjid}|{query.seq}"
            replies_map = self.site_replies.get("replies", {})
            default_reply = self.site_replies.get("_default", ["ANSWERED", "Data verified against source documents. No change."])

            if lookup_key in replies_map:
                reply_status, reply_msg = replies_map[lookup_key]
            else:
                reply_status, reply_msg = default_reply

            query.status = reply_status
            query.response = reply_msg

            self.memory.register_query(query)
            queries.append(query)

            # Record site issue for risk tracking
            self.memory.record_site_issue(f.site, f.code)

            self.trace.record(
                cut=cut,
                protocol_version=protocol_version,
                node="data_manager",
                decision_id=f"DEC-DM-QUERY-{query.query_id}",
                action="DISPATCH_QUERY",
                finding_id=f.finding_id,
                subject=query.usubjid,
                site=f.site,
                reason=f"Created actionable data query: '{actionable_text}'. Site status: {reply_status}.",
                evidence_refs=[ev.model_dump()],
                details={
                    "query_id": query.query_id,
                    "status": query.status,
                    "site_response": query.response,
                },
            )

        return queries

    def _build_query_text(self, finding: Finding, ev) -> str:
        """Construct a precise, single-action query string."""
        if finding.code == "AE_BEFORE_FIRST_DOSE":
            return (
                f"AE onset date in {ev.domain} record #{ev.seq} occurs before the subject's first study dose date. "
                f"Please verify the AE start date against source documents and correct or confirm."
            )
        elif finding.code == "DATA_MALFORMED_LAB_VALUE":
            return (
                f"Laboratory record #{ev.seq} contains non-numeric result. "
                f"Please provide numeric measurement or confirm test was not done."
            )
        elif finding.code == "MISSING_DOSE_RECORD":
            return (
                f"Subject randomized with first dose date recorded in DM but missing exposure records in EX. "
                f"Please submit completed dose administration logs."
            )
        return (
            f"Data discrepancy detected in {ev.domain} record #{ev.seq}: {finding.rationale}. "
            f"Please verify against source documentation and correct or confirm."
        )


# Alias for Stage 2 class nomenclature
DataManager = DataManagerNode

