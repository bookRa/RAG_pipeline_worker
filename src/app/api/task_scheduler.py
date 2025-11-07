from __future__ import annotations

from typing import Callable

from fastapi import BackgroundTasks

from ..application.interfaces import TaskScheduler


class BackgroundTaskScheduler(TaskScheduler):
    """Adapter that schedules callables on FastAPI's BackgroundTasks."""

    def __init__(self, background_tasks: BackgroundTasks) -> None:
        self._background_tasks = background_tasks

    def schedule(self, func: Callable[[], None]) -> None:
        self._background_tasks.add_task(func)
