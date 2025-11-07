from __future__ import annotations

from typing import Callable, Protocol


class TaskScheduler(Protocol):
    """Port describing how background work should be scheduled."""

    def schedule(self, func: Callable[[], None]) -> None:
        """Schedule the provided callable for asynchronous execution."""
