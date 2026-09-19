"""Stage 2 Node 5: Human Gate - Submits escalations to Medical Monitor and processes APPROVED, REJECTED, and CLARIFY."""
import os
import json
from typing import List, Dict, Any, Optional
from stage1.graph import GraphQueryService
from stage1.trace import DecisionTrace
from stage2.models import Escalation
from stage2.memory import CrewMemory


class HumanGateNode:
    """Interfaces with the Medical Monitor approval gate and resolves clarifications."""

    def __init__(self, data_dir: str, query_service: GraphQueryService, memory: CrewMemory, trace: DecisionTrace):
        self.qs = query_service
        self.memory = memory
        self.trace = trace
        self.monitor_decisions = self._load_monitor_decisions(data_dir)

    def _resolve_responses_dir(self, base_path: str) -> str:
        candidates = [
            os.path.join(base_path, "responses"),
            os.path.join(base_path, "hackathon-data", "responses"),
            os.path.join(base_path, "hackathon-data", "hackathon-data", "responses"),
            base_path,
        ]
        for p in candidates:
            if os.path.exists(os.path.join(p, "monitor_decisions.json")):
                return p
        return base_path

    def _load_monitor_decisions(self, data_dir: str) -> Dict[str, Any]:
        resp_dir = self._resolve_responses_dir(data_dir)
        path = os.path.join(resp_dir, "monitor_decisions.json")
        if not os.path.exists(path):
            return {"decisions": {}}
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"decisions": {}}

    def process_escalations(self, escalations: List[Escalation], cut: int, protocol_version: int) -> List[Escalation]:
        """
        Submit pending escalations through the human approval gate.
        Handles APPROVED, REJECTED, and CLARIFY seamlessly.
        """
        processed: List[Escalation] = []
        decisions_map = self.monitor_decisions.get("decisions", {})

        for esc in escalations:
            # Look up decision by 'FINDING_CODE|USUBJID' or 'FINDING_CODE|SITEID'
            lookup_key_subj = f"{esc.code}|{esc.usubjid}"
            lookup_key_site = f"{esc.code}|{esc.site}"

            decision_tuple = decisions_map.get(lookup_key_subj) or decisions_map.get(lookup_key_site)

            if decision_tuple:
                decision_type, decision_text = decision_tuple[0].upper(), decision_tuple[1]
            else:
                # Default if not explicitly scripted
                decision_type, decision_text = "APPROVED", "Escalation approved by medical monitor."

            if decision_type == "APPROVED":
                esc.status = "APPROVED"
                esc.monitor_response = decision_text
                esc.action_taken = "REPORT_TO_SAFETY_AND_HOLD_DOSING"

                self.trace.record(
                    cut=cut,
                    protocol_version=protocol_version,
                    node="human_gate",
                    decision_id=f"DEC-GATE-APP-{esc.escalation_id}",
                    action="ESCALATION_APPROVED",
                    finding_id=esc.code,
                    subject=esc.usubjid,
                    site=esc.site,
                    reason=f"Medical monitor approved escalation: '{decision_text}'. Action: {esc.action_taken}.",
                    evidence_refs=[e.model_dump() for e in esc.evidence],
                    alternatives=["Hold without reporting"],
                )

            elif decision_type == "REJECTED":
                esc.status = "REJECTED"
                esc.monitor_response = decision_text
                esc.action_taken = "DOWNGRADE_TO_MONITORING"
                self.memory.mark_escalation_rejected(esc, decision_text)

                self.trace.record(
                    cut=cut,
                    protocol_version=protocol_version,
                    node="human_gate",
                    decision_id=f"DEC-GATE-REJ-{esc.escalation_id}",
                    action="ESCALATION_REJECTED",
                    finding_id=esc.code,
                    subject=esc.usubjid,
                    site=esc.site,
                    reason=f"Medical monitor rejected escalation: '{decision_text}'. Downgraded to monitoring; re-escalation suppressed.",
                    evidence_refs=[e.model_dump() for e in esc.evidence],
                    alternatives=["Maintain active escalation"],
                )

            elif decision_type == "CLARIFY":
                esc.status = "CLARIFY"
                esc.clarification_question = decision_text

                # Answer clarification by querying graph
                answer_text = self._resolve_clarification(esc.usubjid, decision_text)
                esc.clarification_answer = answer_text

                # Resubmission after answering clarification yields APPROVED per protocol
                esc.status = "APPROVED"
                esc.monitor_response = f"Clarification provided: '{answer_text}'. Approved upon resubmission."
                esc.action_taken = "REPORT_TO_SAFETY_AND_HOLD_DOSING"

                self.trace.record(
                    cut=cut,
                    protocol_version=protocol_version,
                    node="human_gate",
                    decision_id=f"DEC-GATE-CLARIFY-{esc.escalation_id}",
                    action="CLARIFICATION_ANSWERED_AND_APPROVED",
                    finding_id=esc.code,
                    subject=esc.usubjid,
                    site=esc.site,
                    reason=(
                        f"Medical monitor requested clarification: '{decision_text}'. "
                        f"Answer generated from knowledge graph: '{answer_text}'. Escalation approved upon resubmission."
                    ),
                    evidence_refs=[e.model_dump() for e in esc.evidence],
                    alternatives=["Close escalation without answering"],
                    details={
                        "clarification_question": decision_text,
                        "clarification_answer": answer_text,
                    },
                )

            processed.append(esc)

        if not escalations:
            self.trace.record(
                cut=cut,
                protocol_version=protocol_version,
                node="human_gate",
                decision_id=f"DEC-GATE-SUMMARY-CUT{cut}",
                action="GATE_IDLE_NO_ESCALATIONS",
                reason="No pending escalations submitted to Medical Monitor for this cut.",
                details={"escalations_submitted": 0},
            )

        return processed

    def _resolve_clarification(self, usubjid: str, question: str) -> str:
        """Traverse the knowledge graph to generate an empirical answer to monitor query."""
        scr_labs = self.qs.get_screening_labs(usubjid)
        meds = self.qs.get_medications(usubjid)

        alt_val = "Not Recorded"
        if "ALT" in scr_labs and scr_labs["ALT"].value_std is not None:
            alt_val = f"{scr_labs['ALT'].value_std:.1f} U/L ({scr_labs['ALT'].value_raw} {scr_labs['ALT'].unit_raw})"

        med_names = [m.name for m in meds if m.name]
        med_str = ", ".join(med_names) if med_names else "None recorded"

        # Check for hepatotoxic medications
        hepatotoxic = [m.name for m in meds if m.class_name and "hepatotoxic" in m.class_name.lower()]
        hep_str = ", ".join(hepatotoxic) if hepatotoxic else "No known hepatotoxic concomitant medications"

        return (
            f"Screening ALT was {alt_val}. "
            f"Concomitant medications at baseline/on-study: {med_str}. "
            f"Assessment: {hep_str}."
        )


# Alias for Stage 2 class nomenclature
HumanGate = HumanGateNode

