"""Incremental graph synchronizer applying cut-based additions, updates, and corrections."""
from typing import Dict, List, Any, Set, Tuple
from stage1.models import (
    Subject, AdverseEvent, LabResult, VitalSign, Dose, Medication, Finding
)
from stage1.graph import StudyGraph
from stage1.data_loader import DataLoader
from stage1.trace import DecisionTrace


class IncrementalGraphEngine:
    """Incrementally updates StudyGraph with delta records and corrections across cuts."""

    def __init__(self, data_loader: DataLoader, trace: DecisionTrace):
        self.data_loader = data_loader
        self.trace = trace
        self.applied_corrections_count: int = 0
        self.invalidated_findings_count: int = 0

    def apply_cut_delta(
        self,
        graph: StudyGraph,
        cut: int,
        protocol_version: int,
    ) -> Dict[str, Any]:
        """
        Incrementally loads delta records for 'cut' and applies 'corrections.csv' changes for 'cut'.
        Returns a delta summary dict.
        """
        # 1. Load domain records where cut_available == cut
        raw_dm = self.data_loader.load_raw_domain("DM.csv")
        raw_ae = self.data_loader.load_raw_domain("AE.csv")
        raw_lb = self.data_loader.load_raw_domain("LB.csv")
        raw_vs = self.data_loader.load_raw_domain("VS.csv")
        raw_ex = self.data_loader.load_raw_domain("EX.csv")
        raw_cm = self.data_loader.load_raw_domain("CM.csv")

        # 2. Load corrections specific to this cut
        cut_corrections = self.data_loader.load_corrections(max_cut=cut)
        this_cut_corrs = [c for c in cut_corrections if c["cut"] == cut]

        # Apply corrections to graph nodes
        affected_subjects: Set[str] = set()
        for corr in this_cut_corrs:
            domain = corr["domain"]
            usubjid = corr["usubjid"]
            seq = corr["seq"]
            field = corr["field"]
            new_val = corr["new_value"]
            old_val = corr["old_value"]
            reason = corr["reason"]

            affected_subjects.add(usubjid)
            self.applied_corrections_count += 1

            # Update in-memory graph entity
            if domain == "LB":
                labs = graph.labs.get(usubjid, [])
                for lb in labs:
                    if lb.seq == seq:
                        lb.value_raw = str(new_val)
                        lb.value_num = self.data_loader.parse_float(new_val)
                        lb.is_reissued = True
                        if lb.unit_raw and lb.unit_raw.lower() in ["ukat/l", "µkat/l"] and lb.test_code in ["ALT", "AST"]:
                            lb.value_std = lb.value_num * 60.0 if lb.value_num is not None else None
                        else:
                            lb.value_std = lb.value_num

            elif domain == "AE":
                aes = graph.aes.get(usubjid, [])
                for ae in aes:
                    if ae.seq == seq:
                        if field == "AESTDTC":
                            ae.start_date = self.data_loader.parse_date(new_val)
                        elif field == "AEENDTC":
                            ae.end_date = self.data_loader.parse_date(new_val)
                        elif field == "AESER":
                            ae.serious = str(new_val).upper()
                        elif field == "AESHOSP":
                            ae.hospitalisation = str(new_val).upper()

            self.trace.record(
                cut=cut,
                protocol_version=protocol_version,
                node="incremental_graph",
                decision_id=f"DEC-CORR-{domain}-{usubjid}-{seq}-CUT{cut}",
                action="APPLY_INCREMENTAL_CORRECTION",
                subject=usubjid,
                reason=f"Applied retroactive correction in {domain} #{seq} field '{field}' ({old_val} -> {new_val}). Reason: {reason}.",
                details=corr,
            )

        # Invalidate cached derived findings for affected subjects
        for subj in affected_subjects:
            if subj in graph.findings_by_subject:
                self.invalidated_findings_count += len(graph.findings_by_subject[subj])
                graph.findings_by_subject[subj] = []

        # 3. Add new records available at this cut
        new_subjects_count = 0
        new_ae_count = 0
        new_lb_count = 0
        new_vs_count = 0
        new_ex_count = 0
        new_cm_count = 0

        # DM Additions
        for r in raw_dm:
            if int(r.get("cut_available", 1) or 1) == cut:
                usubjid = r.get("USUBJID", "")
                if usubjid and usubjid not in graph.subjects:
                    subj = Subject(
                        usubjid=usubjid,
                        siteid=r.get("SITEID", ""),
                        country=r.get("COUNTRY"),
                        age=self.data_loader.parse_float(r.get("AGE")),
                        sex=r.get("SEX"),
                        dminit=r.get("DMINIT"),
                        brthdtc=self.data_loader.parse_date(r.get("BRTHDTC")),
                        arm=r.get("ARM"),
                        rfstdtc=self.data_loader.parse_date(r.get("RFSTDTC")),
                        scr_hba1c=self.data_loader.parse_float(r.get("SCR_HBA1C")),
                        cut_available=cut,
                    )
                    graph.add_subject(subj)
                    new_subjects_count += 1

        # AE Additions
        for r in raw_ae:
            if int(r.get("cut_available", 1) or 1) == cut:
                usubjid = r.get("USUBJID", "")
                seq = int(r.get("AESEQ", 1) or 1)
                ae = AdverseEvent(
                    usubjid=usubjid,
                    seq=seq,
                    term=r.get("AETERM", ""),
                    severity=r.get("AESEV"),
                    serious=r.get("AESER", "N").upper(),
                    hospitalisation=r.get("AESHOSP", "N").upper(),
                    start_date=self.data_loader.parse_date(r.get("AESTDTC")),
                    end_date=self.data_loader.parse_date(r.get("AEENDTC")),
                    outcome=r.get("AEOUT"),
                    narrative=r.get("AENARR"),
                    cut_available=cut,
                )
                graph.add_adverse_event(ae)
                new_ae_count += 1

        # LB Additions
        for r in raw_lb:
            if int(r.get("cut_available", 1) or 1) == cut:
                usubjid = r.get("USUBJID", "")
                seq = int(r.get("LBSEQ", 1) or 1)
                test_code = r.get("LBTESTCD", "").strip().upper()
                unit_raw = r.get("LBORRESU", "").strip()
                val_raw = r.get("LBORRES")
                val_num = self.data_loader.parse_float(val_raw)

                val_std = val_num
                unit_std = unit_raw
                if unit_raw.lower() in ["ukat/l", "µkat/l"] and test_code in ["ALT", "AST"]:
                    if val_num is not None:
                        val_std = val_num * 60.0
                        unit_std = "U/L"

                lb = LabResult(
                    usubjid=usubjid,
                    seq=seq,
                    visit=r.get("VISIT"),
                    date=self.data_loader.parse_date(r.get("LBDTC")),
                    test_code=test_code,
                    value_raw=str(val_raw) if val_raw is not None else None,
                    unit_raw=unit_raw,
                    value_num=val_num,
                    unit_std=unit_std,
                    value_std=val_std,
                    cut_available=cut,
                )
                graph.add_lab_result(lb)
                new_lb_count += 1

        # VS Additions
        for r in raw_vs:
            if int(r.get("cut_available", 1) or 1) == cut:
                usubjid = r.get("USUBJID", "")
                seq = int(r.get("VSSEQ", 1) or 1)
                vs = VitalSign(
                    usubjid=usubjid,
                    seq=seq,
                    visit=r.get("VISIT"),
                    date=self.data_loader.parse_date(r.get("VSDTC")),
                    test_code=r.get("VSTESTCD", "").strip().upper(),
                    value_raw=r.get("VSORRES"),
                    unit_raw=r.get("VSORRESU"),
                    value_num=self.data_loader.parse_float(r.get("VSORRES")),
                    cut_available=cut,
                )
                graph.add_vital_sign(vs)
                new_vs_count += 1

        # EX Additions
        for r in raw_ex:
            if int(r.get("cut_available", 1) or 1) == cut:
                usubjid = r.get("USUBJID", "")
                seq = int(r.get("EXSEQ", 1) or 1)
                ex = Dose(
                    usubjid=usubjid,
                    seq=seq,
                    dose=self.data_loader.parse_float(r.get("EXDOSE")),
                    dose_unit=r.get("EXDOSU"),
                    start_date=self.data_loader.parse_date(r.get("EXSTDTC")),
                    end_date=self.data_loader.parse_date(r.get("EXENDTC")),
                    cut_available=cut,
                )
                graph.add_dose(ex)
                new_ex_count += 1

        # CM Additions
        for r in raw_cm:
            if int(r.get("cut_available", 1) or 1) == cut:
                usubjid = r.get("USUBJID", "")
                seq = int(r.get("CMSEQ", 1) or 1)
                cm = Medication(
                    usubjid=usubjid,
                    seq=seq,
                    name=r.get("CMTRT"),
                    class_name=r.get("CMCLAS", "").strip(),
                    start_date=self.data_loader.parse_date(r.get("CMSTDTC")),
                    end_date=self.data_loader.parse_date(r.get("CMENDTC")),
                    cut_available=cut,
                )
                graph.add_medication(cm)
                new_cm_count += 1

        return {
            "cut": cut,
            "new_subjects": new_subjects_count,
            "new_aes": new_ae_count,
            "new_labs": new_lb_count,
            "new_vitals": new_vs_count,
            "new_doses": new_ex_count,
            "new_medications": new_cm_count,
            "corrections_applied": len(this_cut_corrs),
            "affected_subjects": list(affected_subjects),
        }
