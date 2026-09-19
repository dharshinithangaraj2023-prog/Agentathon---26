"""Dynamic, schema-driven data loader and normalizer for study domains."""
import os
import csv
import re
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
from stage1.models import (
    Subject, AdverseEvent, LabResult, VitalSign, Dose,
    Medication, Disposition, MedicalHistory, ECG
)


class DataLoader:
    """Loads, normalizes, and filters study data from CSVs."""

    def __init__(self, data_dir: str):
        self.data_dir = self._resolve_data_dir(data_dir)
        self.reference_ranges = self._load_reference_ranges()
        self.cuts_meta = self._load_cuts_meta()

    def _resolve_data_dir(self, base_path: str) -> str:
        """Find the exact directory containing domain CSV files."""
        candidates = [
            os.path.join(base_path, "data"),
            os.path.join(base_path, "hackathon-data", "data"),
            os.path.join(base_path, "hackathon-data", "hackathon-data", "data"),
            base_path,
        ]
        for path in candidates:
            if os.path.exists(os.path.join(path, "DM.csv")):
                return path
        return base_path

    @staticmethod
    def parse_date(val: Optional[str]) -> Optional[str]:
        """Normalize varied date formats (e.g. '2026-01-15', '03-FEB-2026') to 'YYYY-MM-DD'."""
        if not val or not str(val).strip():
            return None
        val_str = str(val).strip()
        # Format: 2026-01-15
        if re.match(r"^\d{4}-\d{2}-\d{2}$", val_str):
            return val_str
        # Format: 03-FEB-2026 or 3-FEB-2026
        match = re.match(r"^(\d{1,2})-([A-Za-z]{3})-(\d{4})$", val_str)
        if match:
            day, mon, year = match.groups()
            try:
                dt = datetime.strptime(f"{int(day):02d}-{mon.upper()}-{year}", "%d-%b-%Y")
                return dt.strftime("%Y-%m-%d")
            except Exception:
                pass
        # Format: 2026/01/15
        match = re.match(r"^(\d{4})/(\d{1,2})/(\d{1,2})$", val_str)
        if match:
            y, m, d = match.groups()
            return f"{y}-{int(m):02d}-{int(d):02d}"
        return val_str

    @staticmethod
    def parse_float(val: Optional[str]) -> Optional[float]:
        """Safely parse float, returning None for non-numeric/missing strings like '<5', 'ND'."""
        if val is None:
            return None
        s = str(val).strip()
        if not s or s.upper() in ["ND", "BLANK", "NA", "N/A", "NULL"]:
            return None
        # Handle prefixes like '<' or '>'
        if s.startswith("<") or s.startswith(">"):
            return None
        try:
            return float(s)
        except ValueError:
            return None

    def _load_reference_ranges(self) -> Dict[str, Dict[str, Any]]:
        """Load laboratory reference ranges by (LBTESTCD, LAB)."""
        ref_path = os.path.join(self.data_dir, "reference_ranges.csv")
        ranges = {}
        if not os.path.exists(ref_path):
            return ranges
        with open(ref_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                test = row.get("LBTESTCD", "").strip().upper()
                lab = row.get("LAB", "CENTRAL").strip().upper()
                unit = row.get("UNIT", "").strip()
                low = self.parse_float(row.get("LOW"))
                high = self.parse_float(row.get("HIGH"))
                key = f"{test}|{lab}"
                ranges[key] = {
                    "test": test,
                    "lab": lab,
                    "unit": unit,
                    "low": low,
                    "high": high,
                }
                # Also store default under test
                if test not in ranges or lab == "CENTRAL":
                    ranges[test] = ranges[key]
        return ranges

    def _load_cuts_meta(self) -> Dict[int, Dict[str, Any]]:
        """Load protocol version mapping per cut from cuts.csv."""
        cuts_path = os.path.join(self.data_dir, "cuts.csv")
        cuts = {}
        if not os.path.exists(cuts_path):
            return cuts
        with open(cuts_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    c = int(row.get("cut", 1))
                    pv = int(row.get("protocol_version", 1))
                    new_rec = int(row.get("new_records", 0))
                    corrs = int(row.get("corrections", 0))
                    cuts[c] = {
                        "cut": c,
                        "protocol_version": pv,
                        "new_records": new_rec,
                        "corrections": corrs,
                    }
                except Exception:
                    continue
        return cuts

    def get_protocol_version_for_cut(self, cut: int) -> int:
        """Return the active protocol version for the given cut."""
        if cut in self.cuts_meta:
            return self.cuts_meta[cut]["protocol_version"]
        # Default schedule based on standard rules
        if cut >= 9:
            return 3
        if cut >= 5:
            return 2
        return 1

    def load_corrections(self, max_cut: Optional[int] = None) -> List[Dict[str, Any]]:
        """Load corrections from corrections.csv up to max_cut."""
        corr_path = os.path.join(self.data_dir, "corrections.csv")
        corrections = []
        if not os.path.exists(corr_path):
            return corrections
        with open(corr_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    c = int(row.get("cut", 1))
                    if max_cut is not None and c > max_cut:
                        continue
                    corrections.append({
                        "cut": c,
                        "domain": row.get("domain", "").strip().upper(),
                        "usubjid": row.get("usubjid", "").strip(),
                        "seq": int(row.get("seq", 0)),
                        "field": row.get("field", "").strip(),
                        "old_value": row.get("old_value", ""),
                        "new_value": row.get("new_value", ""),
                        "reason": row.get("reason", "").strip(),
                    })
                except Exception:
                    continue
        return corrections

    def load_raw_domain(self, domain_filename: str) -> List[Dict[str, Any]]:
        """Generic reader for any CSV domain file, dynamically discovering columns."""
        path = os.path.join(self.data_dir, domain_filename)
        if not os.path.exists(path):
            return []
        rows = []
        with open(path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for r in reader:
                rows.append({k.strip(): (v.strip() if v is not None else "") for k, v in r.items()})
        return rows

    def load_all_domains(self, cut: Optional[int] = None, apply_corrections: bool = True) -> Dict[str, List[Any]]:
        """
        Load all clinical domains up to the specified cut, normalizing fields
        and optionally applying retroactive corrections.
        """
        raw_dm = self.load_raw_domain("DM.csv")
        raw_ae = self.load_raw_domain("AE.csv")
        raw_lb = self.load_raw_domain("LB.csv")
        raw_vs = self.load_raw_domain("VS.csv")
        raw_ex = self.load_raw_domain("EX.csv")
        raw_cm = self.load_raw_domain("CM.csv")
        raw_ds = self.load_raw_domain("DS.csv")
        raw_mh = self.load_raw_domain("MH.csv")
        raw_eg = self.load_raw_domain("EG.csv")

        # Track active corrections lookup: (domain, usubjid, seq, field) -> new_value
        active_corrections: Dict[Tuple[str, str, int, str], Any] = {}
        if apply_corrections:
            for corr in self.load_corrections(max_cut=cut):
                key = (corr["domain"], corr["usubjid"], corr["seq"], corr["field"])
                active_corrections[key] = corr["new_value"]

        # Parse Subjects (DM)
        subjects: List[Subject] = []
        for r in raw_dm:
            cut_avail = int(r.get("cut_available", 1) or 1)
            if cut is not None and cut_avail > cut:
                continue
            usubjid = r.get("USUBJID", "")
            if not usubjid:
                continue
            corr_cut = int(r["corrected_at_cut"]) if r.get("corrected_at_cut") else None
            subj = Subject(
                usubjid=usubjid,
                siteid=r.get("SITEID", ""),
                country=r.get("COUNTRY"),
                age=self.parse_float(r.get("AGE")),
                sex=r.get("SEX"),
                dminit=r.get("DMINIT"),
                brthdtc=self.parse_date(r.get("BRTHDTC")),
                arm=r.get("ARM"),
                rfstdtc=self.parse_date(r.get("RFSTDTC")),
                scr_hba1c=self.parse_float(r.get("SCR_HBA1C")),
                cut_available=cut_avail,
                corrected_at_cut=corr_cut,
            )
            subjects.append(subj)

        # Parse Adverse Events (AE)
        adverse_events: List[AdverseEvent] = []
        for r in raw_ae:
            cut_avail = int(r.get("cut_available", 1) or 1)
            if cut is not None and cut_avail > cut:
                continue
            usubjid = r.get("USUBJID", "")
            seq = int(r.get("AESEQ", 1) or 1)
            corr_cut = int(r["corrected_at_cut"]) if r.get("corrected_at_cut") else None

            # Check corrections
            term = active_corrections.get(("AE", usubjid, seq, "AETERM"), r.get("AETERM", ""))
            start_date = active_corrections.get(("AE", usubjid, seq, "AESTDTC"), r.get("AESTDTC"))
            end_date = active_corrections.get(("AE", usubjid, seq, "AEENDTC"), r.get("AEENDTC"))
            aeser = active_corrections.get(("AE", usubjid, seq, "AESER"), r.get("AESER", "N"))
            aeshosp = active_corrections.get(("AE", usubjid, seq, "AESHOSP"), r.get("AESHOSP", "N"))

            ae = AdverseEvent(
                usubjid=usubjid,
                seq=seq,
                term=term,
                severity=r.get("AESEV"),
                serious=aeser.upper() if aeser else "N",
                hospitalisation=aeshosp.upper() if aeshosp else "N",
                start_date=self.parse_date(start_date),
                end_date=self.parse_date(end_date),
                outcome=r.get("AEOUT"),
                narrative=r.get("AENARR"),
                cut_available=cut_avail,
                corrected_at_cut=corr_cut,
            )
            adverse_events.append(ae)

        # Parse Labs (LB)
        labs: List[LabResult] = []
        for r in raw_lb:
            cut_avail = int(r.get("cut_available", 1) or 1)
            if cut is not None and cut_avail > cut:
                continue
            usubjid = r.get("USUBJID", "")
            seq = int(r.get("LBSEQ", 1) or 1)
            test_code = r.get("LBTESTCD", "").strip().upper()
            unit_raw = r.get("LBORRESU", "").strip()
            corr_cut = int(r["corrected_at_cut"]) if r.get("corrected_at_cut") else None

            val_raw = active_corrections.get(("LB", usubjid, seq, "LBORRES"), r.get("LBORRES"))
            is_reissued = ("LB", usubjid, seq, "LBORRES") in active_corrections
            val_num = self.parse_float(val_raw)

            # Unit Standardization:
            # S07 or local lab reporting ALT/AST in ukat/L: 1 ukat/L = 60 U/L
            val_std = val_num
            unit_std = unit_raw
            if unit_raw.lower() in ["ukat/l", "µkat/l", "ukat", "µkat"] and test_code in ["ALT", "AST"]:
                if val_num is not None:
                    val_std = val_num * 60.0
                    unit_std = "U/L"

            lb = LabResult(
                usubjid=usubjid,
                seq=seq,
                visit=r.get("VISIT"),
                date=self.parse_date(r.get("LBDTC")),
                test_code=test_code,
                value_raw=str(val_raw) if val_raw is not None else None,
                unit_raw=unit_raw,
                value_num=val_num,
                unit_std=unit_std,
                value_std=val_std,
                cut_available=cut_avail,
                corrected_at_cut=corr_cut,
                is_reissued=is_reissued,
            )
            labs.append(lb)

        # Parse Vital Signs (VS)
        vitals: List[VitalSign] = []
        for r in raw_vs:
            cut_avail = int(r.get("cut_available", 1) or 1)
            if cut is not None and cut_avail > cut:
                continue
            usubjid = r.get("USUBJID", "")
            seq = int(r.get("VSSEQ", 1) or 1)
            corr_cut = int(r["corrected_at_cut"]) if r.get("corrected_at_cut") else None
            val_raw = active_corrections.get(("VS", usubjid, seq, "VSORRES"), r.get("VSORRES"))
            vs = VitalSign(
                usubjid=usubjid,
                seq=seq,
                visit=r.get("VISIT"),
                date=self.parse_date(r.get("VSDTC")),
                test_code=r.get("VSTESTCD", "").strip().upper(),
                value_raw=str(val_raw) if val_raw is not None else None,
                unit_raw=r.get("VSORRESU"),
                value_num=self.parse_float(val_raw),
                cut_available=cut_avail,
                corrected_at_cut=corr_cut,
            )
            vitals.append(vs)

        # Parse Exposure / Doses (EX)
        doses: List[Dose] = []
        for r in raw_ex:
            cut_avail = int(r.get("cut_available", 1) or 1)
            if cut is not None and cut_avail > cut:
                continue
            usubjid = r.get("USUBJID", "")
            seq = int(r.get("EXSEQ", 1) or 1)
            corr_cut = int(r["corrected_at_cut"]) if r.get("corrected_at_cut") else None
            dose_val = active_corrections.get(("EX", usubjid, seq, "EXDOSE"), r.get("EXDOSE"))
            ex = Dose(
                usubjid=usubjid,
                seq=seq,
                dose=self.parse_float(dose_val),
                dose_unit=r.get("EXDOSU"),
                start_date=self.parse_date(r.get("EXSTDTC")),
                end_date=self.parse_date(r.get("EXENDTC")),
                cut_available=cut_avail,
                corrected_at_cut=corr_cut,
            )
            doses.append(ex)

        # Parse Concomitant Medications (CM)
        meds: List[Medication] = []
        for r in raw_cm:
            cut_avail = int(r.get("cut_available", 1) or 1)
            if cut is not None and cut_avail > cut:
                continue
            usubjid = r.get("USUBJID", "")
            seq = int(r.get("CMSEQ", 1) or 1)
            corr_cut = int(r["corrected_at_cut"]) if r.get("corrected_at_cut") else None
            cm = Medication(
                usubjid=usubjid,
                seq=seq,
                name=r.get("CMTRT"),
                class_name=r.get("CMCLAS", "").strip(),
                start_date=self.parse_date(r.get("CMSTDTC")),
                end_date=self.parse_date(r.get("CMENDTC")),
                cut_available=cut_avail,
                corrected_at_cut=corr_cut,
            )
            meds.append(cm)

        # Parse Dispositions (DS)
        dispositions: List[Disposition] = []
        for r in raw_ds:
            cut_avail = int(r.get("cut_available", 1) or 1)
            if cut is not None and cut_avail > cut:
                continue
            usubjid = r.get("USUBJID", "")
            seq = int(r.get("DSSEQ", 1) or 1)
            corr_cut = int(r["corrected_at_cut"]) if r.get("corrected_at_cut") else None
            ds = Disposition(
                usubjid=usubjid,
                seq=seq,
                term=r.get("DSTERM"),
                decod=r.get("DSDECOD"),
                date=self.parse_date(r.get("DSSTDTC")),
                cut_available=cut_avail,
                corrected_at_cut=corr_cut,
            )
            dispositions.append(ds)

        # Parse Medical History (MH)
        mh_list: List[MedicalHistory] = []
        for r in raw_mh:
            cut_avail = int(r.get("cut_available", 1) or 1)
            if cut is not None and cut_avail > cut:
                continue
            usubjid = r.get("USUBJID", "")
            seq = int(r.get("MHSEQ", 1) or 1)
            corr_cut = int(r["corrected_at_cut"]) if r.get("corrected_at_cut") else None
            mh = MedicalHistory(
                usubjid=usubjid,
                seq=seq,
                term=r.get("MHTERM"),
                decod=r.get("MHDECOD"),
                cut_available=cut_avail,
                corrected_at_cut=corr_cut,
            )
            mh_list.append(mh)

        # Parse ECG (EG)
        ecg_list: List[ECG] = []
        for r in raw_eg:
            cut_avail = int(r.get("cut_available", 1) or 1)
            if cut is not None and cut_avail > cut:
                continue
            usubjid = r.get("USUBJID", "")
            seq = int(r.get("EGSEQ", 1) or 1)
            corr_cut = int(r["corrected_at_cut"]) if r.get("corrected_at_cut") else None
            eg = ECG(
                usubjid=usubjid,
                seq=seq,
                visit=r.get("VISIT"),
                date=self.parse_date(r.get("EGDTC")),
                test_code=r.get("EGTESTCD", "").strip().upper(),
                value_raw=r.get("EGORRES"),
                unit_raw=r.get("EGORRESU"),
                value_num=self.parse_float(r.get("EGORRES")),
                cut_available=cut_avail,
                corrected_at_cut=corr_cut,
            )
            ecg_list.append(eg)

        return {
            "DM": subjects,
            "AE": adverse_events,
            "LB": labs,
            "VS": vitals,
            "EX": doses,
            "CM": meds,
            "DS": dispositions,
            "MH": mh_list,
            "EG": ecg_list,
        }
