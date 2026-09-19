"""Global execution and token budget manager with graceful tiered degradation."""
import time
from stage3.models import BudgetStatus


class BudgetManager:
    """Tracks global execution time and model tokens, degrading gracefully under pressure."""

    def __init__(self, max_seconds: float = 300.0, max_tokens: int = 100000):
        self.max_seconds = max_seconds
        self.max_tokens = max_tokens
        self.start_time: float = time.time()
        self.tokens_used: int = 0
        self.expensive_ops_count: int = 0
        self.cheap_ops_count: int = 0

    def start(self):
        """Reset the budget start timer."""
        self.start_time = time.time()

    def record_operation(self, op_name: str, tokens: int = 0, is_expensive: bool = False):
        """Log an operation and its consumed resource cost."""
        self.tokens_used += tokens
        if is_expensive:
            self.expensive_ops_count += 1
        else:
            self.cheap_ops_count += 1

    def get_elapsed_seconds(self) -> float:
        return time.time() - self.start_time

    def get_percent_consumed(self) -> float:
        time_ratio = self.get_elapsed_seconds() / max(self.max_seconds, 1.0)
        token_ratio = self.tokens_used / max(self.max_tokens, 1)
        return min(max(time_ratio, token_ratio) * 100.0, 100.0)

    def get_tier(self) -> str:
        """
        FULL: 0% - 79% consumed
        REDUCED: 80% - 94% consumed (suppress optional narratives)
        MINIMAL: >= 95% consumed (critical safety & graph delta only)
        """
        pct = self.get_percent_consumed()
        if pct >= 95.0:
            return "MINIMAL"
        elif pct >= 80.0:
            return "REDUCED"
        return "FULL"

    def can_run_expensive_op(self) -> bool:
        """Returns False if budget tier requires suppressing expensive narrative/LLM operations."""
        return self.get_tier() == "FULL"

    def get_status(self) -> BudgetStatus:
        return BudgetStatus(
            tier=self.get_tier(),
            elapsed_seconds=round(self.get_elapsed_seconds(), 2),
            max_seconds=self.max_seconds,
            tokens_used=self.tokens_used,
            max_tokens=self.max_tokens,
            expensive_ops_count=self.expensive_ops_count,
            percent_consumed=round(self.get_percent_consumed(), 1),
        )
