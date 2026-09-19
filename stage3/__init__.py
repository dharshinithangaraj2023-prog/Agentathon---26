"""Stage 3 - WATCH: 12-cut unattended surveillance system."""
from stage3.models import (
    Explanation,
    SurveillanceReport,
    AdversarialAlert,
    BudgetStatus,
)
from stage3.watch import StudyWatch, PendingEscalationStore
from stage3.budget import BudgetManager
from stage3.adversarial import AdversarialEngine, AdversarialDetector
from stage3.incremental_graph import IncrementalGraphEngine
from stage3.explanation import ExplanationEngine
from stage3.reporting import ReportGenerator

# Alias for Stage 3 class nomenclature
IncrementalGraphManager = IncrementalGraphEngine

__all__ = [
    "StudyWatch",
    "IncrementalGraphManager",
    "IncrementalGraphEngine",
    "PendingEscalationStore",
    "AdversarialDetector",
    "AdversarialEngine",
    "BudgetManager",
    "ExplanationEngine",
    "ReportGenerator",
    "Explanation",
    "SurveillanceReport",
    "AdversarialAlert",
    "BudgetStatus",
]
