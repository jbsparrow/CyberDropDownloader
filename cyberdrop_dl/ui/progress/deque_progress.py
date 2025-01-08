from __future__ import annotations

from abc import ABC, abstractmethod
from collections import deque
from itertools import islice
from typing import TYPE_CHECKING

from rich.console import Group
from rich.panel import Panel
from rich.progress import Progress, TaskID

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager


class DequeProgress(ABC):
    progress: Progress
    title: str
    type_str: str = "Files"

    def __init__(self, visible_tasks_limit: int, manager: Manager) -> None:
        self.manager = manager
        self.overflow = Progress("[progress.description]{task.description}")
        self.queue = Progress("[progress.description]{task.description}")
        self.progress_group = Group(self.progress, self.overflow, self.queue)
        self.color = "plum3"
        self.progress_str = "[{color}]{description}"
        self.overflow_str = "[{color}]... And {number} Other {type_str}"
        self.queue_str = "[{color}]... And {number} {type_str} In {title} Queue"
        self.overflow_task_id = self.overflow.add_task(
            self.overflow_str.format(color=self.color, number=0, type_str=self.type_str),
            visible=False,
        )
        self.queue_task_id = self.queue.add_task(
            self.queue_str.format(color=self.color, number=0, type_str=self.type_str, title=self.title),
            visible=False,
        )
        self.tasks: deque[TaskID] = deque([])
        self._tasks_visibility_limit = visible_tasks_limit

    @property
    def visible_tasks(self) -> list[TaskID]:
        if len(self.tasks) > self._tasks_visibility_limit:
            return [self.tasks[i] for i in range(self._tasks_visibility_limit)]
        return list(self.tasks)

    @property
    def invisible_tasks(self) -> list[TaskID]:
        return list(islice(self.tasks, self._tasks_visibility_limit, None))

    @property
    def invisible_tasks_len(self) -> int:
        return max(0, len(self.tasks) - self._tasks_visibility_limit)

    def get_progress(self) -> Panel:
        """Returns the progress bar."""
        return Panel(self.progress_group, title=self.title, border_style="green", padding=(1, 1))

    @abstractmethod
    def get_queue_length(self) -> int: ...

    def redraw(self) -> None:
        """Redraws the progress bar."""
        for task in self.visible_tasks:
            self.progress.update(task, visible=True)

        self.overflow.update(
            self.overflow_task_id,
            description=self.overflow_str.format(
                color=self.color,
                number=self.invisible_tasks_len,
                type_str=self.type_str,
            ),
            visible=self.invisible_tasks_len > 0,
        )

        queue_length = self.get_queue_length()

        self.queue.update(
            self.queue_task_id,
            description=self.queue_str.format(
                color=self.color, number=queue_length, type_str=self.type_str, title=self.title
            ),
            visible=queue_length > 0,
        )

    def add_task(self, description: str, total: float | None = None) -> TaskID:
        """Adds a new task to the progress bar."""
        task_id = self.progress.add_task(
            self.progress_str.format(color=self.color, description=description),
            total=total,
            visible=len(self.visible_tasks) >= self._tasks_visibility_limit,
        )
        self.tasks.append(task_id)
        self.redraw()
        return task_id

    def remove_task(self, task_id: TaskID) -> None:
        """Removes a task from the progress bar."""
        if task_id not in self.tasks:
            msg = "Task ID not found"
            raise ValueError(msg)

        self.tasks.remove(task_id)
        self.progress.remove_task(task_id)
        self.redraw()
