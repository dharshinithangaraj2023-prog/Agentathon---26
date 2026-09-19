"""Protocol document parser with SHA-256 hash tracking and adversarial prompt injection detection."""
import os
import re
import hashlib
from typing import Dict, List, Any, Optional
from stage1.models import DocumentMetadata, ProtocolRule


class DocumentManager:
    """Parses and manages protocol documents, treating them strictly as data, never code."""

    INJECTION_PATTERNS = [
        r"ignore\s+previous\s+instructions",
        r"note\s+to\s+automated\s+reviewers",
        r"automated\s+reviewers\s+should",
        r"accept\s+all\s+values",
        r"exclude\s+this\s+site",
        r"do\s+not\s+flag",
        r"restart\s+the\s+analyser\s+interface",
    ]

    def __init__(self, doc_dir: str):
        self.doc_dir = self._resolve_doc_dir(doc_dir)
        self.doc_history: Dict[str, DocumentMetadata] = {}
        self.protocol_rules: Dict[int, Dict[str, Any]] = self._init_standard_rules()

    def _resolve_doc_dir(self, base_path: str) -> str:
        candidates = [
            os.path.join(base_path, "documents"),
            os.path.join(base_path, "hackathon-data", "documents"),
            os.path.join(base_path, "hackathon-data", "hackathon-data", "documents"),
            base_path,
        ]
        for path in candidates:
            if os.path.exists(os.path.join(path, "protocol_v1.md")):
                return path
        return base_path

    def _init_standard_rules(self) -> Dict[int, Dict[str, Any]]:
        """Base clinical trial rules extracted from validated protocol specs."""
        return {
            1: {
                "version": 1,
                "inclusion": {
                    "age_min": 18,
                    "age_max": 75,
                    "hba1c_min": 7.0,
                    "hba1c_max": 10.5,
                },
                "exclusion": {
                    "alt_ast_uln_multiplier": 2.0,  # Screening ALT or AST > 2x ULN
                    "pregnancy": True,
                    "creatinine_max": None,  # Not in v1
                },
                "visit_window_days": 7,  # +/- 7 days
                "prohibited_med_classes": ["Systemic Glucocorticoid"],
                "hys_law": {
                    "transaminase_uln_mult": 3.0,
                    "bili_uln_mult": 2.0,
                    "window_days": 14,
                },
                "standard_dose": 10.0,
            },
            2: {
                "version": 2,
                "inclusion": {
                    "age_min": 18,
                    "age_max": 75,
                    "hba1c_min": 7.0,
                    "hba1c_max": 10.5,
                },
                "exclusion": {
                    "alt_ast_uln_multiplier": 2.0,
                    "pregnancy": True,
                    "creatinine_max": 1.5,  # Added in v2
                },
                "visit_window_days": 3,  # Tightened to +/- 3 days in v2
                "prohibited_med_classes": ["Systemic Glucocorticoid"],
                "hys_law": {
                    "transaminase_uln_mult": 3.0,
                    "bili_uln_mult": 2.0,
                    "window_days": 14,
                },
                "standard_dose": 10.0,
            },
            3: {
                "version": 3,
                "inclusion": {
                    "age_min": 18,
                    "age_max": 75,
                    "hba1c_min": 7.0,
                    "hba1c_max": 10.5,
                },
                "exclusion": {
                    "alt_ast_uln_multiplier": 2.0,
                    "pregnancy": True,
                    "creatinine_max": 1.5,
                },
                "visit_window_days": 3,
                "prohibited_med_classes": ["Systemic Glucocorticoid", "Sulfonylurea"],  # Added Sulfonylurea in v3
                "hys_law": {
                    "transaminase_uln_mult": 3.0,
                    "bili_uln_mult": 2.0,
                    "window_days": 14,
                },
                "standard_dose": 10.0,
            },
        }

    def inspect_documents(self) -> List[DocumentMetadata]:
        """Read all documents, compute SHA-256 hashes, detect tampering / prompt injections."""
        results = []
        if not os.path.exists(self.doc_dir):
            return results

        for filename in sorted(os.listdir(self.doc_dir)):
            if not filename.endswith(".md"):
                continue
            filepath = os.path.join(self.doc_dir, filename)
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()

            sha256 = hashlib.sha256(content.encode("utf-8")).hexdigest()
            prev_meta = self.doc_history.get(filename)
            prev_hash = prev_meta.hash_sha256 if prev_meta else None

            # Scan for adversarial prompt injection text
            ignored_instructions = []
            for pattern in self.INJECTION_PATTERNS:
                matches = re.findall(pattern, content, re.IGNORECASE)
                if matches:
                    ignored_instructions.extend(matches)

            is_tampered = len(ignored_instructions) > 0

            meta = DocumentMetadata(
                doc_name=filename,
                hash_sha256=sha256,
                previous_hash=prev_hash,
                has_tampered_instructions=is_tampered,
                ignored_instructions=list(set(ignored_instructions)),
            )
            self.doc_history[filename] = meta
            results.append(meta)

        return results

    def get_rules_for_version(self, version: int) -> Dict[str, Any]:
        """Return the rules dict for the given protocol version."""
        if version in self.protocol_rules:
            return self.protocol_rules[version]
        return self.protocol_rules.get(max(self.protocol_rules.keys()), self.protocol_rules[1])
