"""Stage 2 trace integration and TraceStore alias for audit logging."""
from stage1.trace import DecisionTrace, TraceEntry

# TraceStore alias for Stage 2
TraceStore = DecisionTrace

__all__ = ["TraceStore", "DecisionTrace", "TraceEntry"]
