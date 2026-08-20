from __future__ import annotations

import time
from typing import Generic, TypeVar


ItemT = TypeVar("ItemT")


class RuleBudgetExceeded(Exception):
    """Stop a rule immediately while preserving items emitted before exhaustion."""

    def __init__(self, code: str, partial_items: list[object]):
        super().__init__(code)
        self.code = code
        self.partial_items = partial_items


class RuleBudget:
    """Shared finding/deadline budget for one scanner invocation."""

    def __init__(self, remaining: int, deadline: float):
        self.remaining = remaining
        self.deadline = deadline

    def checkpoint(self, partial_items: list[object]) -> None:
        if time.monotonic() >= self.deadline:
            raise RuleBudgetExceeded("elapsed_time_limit", partial_items)


class BudgetedList(list[ItemT], Generic[ItemT]):
    """List that aborts its producing rule at the shared hostile-input limit."""

    def __init__(self, budget: RuleBudget | None = None):
        super().__init__()
        self.budget = budget

    def append(self, item: ItemT) -> None:
        if self.budget is not None:
            self.budget.checkpoint(list(self))
            if self.budget.remaining <= 0:
                raise RuleBudgetExceeded("finding_count_limit", list(self))
            self.budget.remaining -= 1
        super().append(item)

    def checkpoint(self) -> None:
        if self.budget is not None:
            self.budget.checkpoint(list(self))
