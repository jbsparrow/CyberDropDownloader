from __future__ import annotations

from abc import ABC, abstractmethod
from collections import deque
from itertools import islice
from typing import TYPE_CHECKING

from rich.console import Group
from rich.panel import Panel
from rich.progress import Progress, TaskID

if TYPE_CHECKING:
    from collections.abc import Sequence


def adjust_title(s: str, length: int = 40, placeholder: str = "...") -> str:
    """Collapse and truncate or pad the given string to fit in the given length."""
    return f"{s[: length - len(placeholder)]}{placeholder}" if len(s) >= length else s.ljust(length)


class DequeProgress(ABC):
    _progress: Progress
    type_str: str = "files"
    color = "plum3"
    progress_str = "[{color}]{description}"
    overflow_str = "[{color}]... and {number:,} other {type_str}"
    queue_str = "[{color}]... and {number:,} {type_str} in {title} queue"

    def __init__(self, title: str, visible_tasks_limit: int) -> None:
        self.title = title
        self.title_lower = title.lower()
        self._overflow = Progress("[progress.description]{task.description}")
        self._queue = Progress("[progress.description]{task.description}")
        self._progress_group = Group(self._progress, self._overflow, self._queue)

        self._overflow_task_id = self._overflow.add_task(
            self.overflow_str.format(color=self.color, number=0, type_str=self.type_str),
            visible=False,
        )
        self._queue_task_id = self._queue.add_task(
            self.queue_str.format(color=self.color, number=0, type_str=self.type_str, title=self.title_lower),
            visible=False,
        )
        self._tasks: deque[TaskID] = deque([])
        self._tasks_visibility_limit = visible_tasks_limit

    @abstractmethod
    def get_queue_length(self) -> int: ...

    @property
    def visible_tasks(self) -> Sequence[TaskID]:
        if len(self._tasks) > self._tasks_visibility_limit:
            return [self._tasks[i] for i in range(self._tasks_visibility_limit)]
        return self._tasks

    @property
    def invisible_tasks(self) -> Sequence[TaskID]:
        return list(islice(self._tasks, self._tasks_visibility_limit, None))

    @property
    def invisible_tasks_len(self) -> int:
        """Faster to compute than `len(self.invisible_tasks)`"""
        return max(0, len(self._tasks) - self._tasks_visibility_limit)

    def has_visible_capacity(self) -> bool:
        return len(self._tasks) < self._tasks_visibility_limit

    def get_renderable(self) -> Panel:
        """Returns the progress bar."""
        return Panel(self._progress_group, title=self.title, border_style="green", padding=(1, 1))

    def add_task(self, description: str, total: float | None = None) -> TaskID:
        """Adds a new task to the progress bar."""
        task_id = self._progress.add_task(
            self.progress_str.format(color=self.color, description=description),
            total=total,
            visible=self.has_visible_capacity(),
        )
        self._tasks.append(task_id)
        self.redraw()
        return task_id

    def remove_task(self, task_id: TaskID) -> None:
        """Removes a task from the progress bar."""
        if task_id not in self._tasks:
            msg = "Task ID not found"
            raise ValueError(msg)

        self._tasks.remove(task_id)
        self._progress.remove_task(task_id)
        self.redraw()

    def redraw(self) -> None:
        """Redraws the progress bar."""
        for task in self.visible_tasks:
            self._progress.update(task, visible=True)

        invisible_tasks_len = self.invisible_tasks_len

        self._overflow.update(
            self._overflow_task_id,
            description=self.overflow_str.format(
                color=self.color,
                number=invisible_tasks_len,
                type_str=self.type_str,
            ),
            visible=invisible_tasks_len > 0,
        )

        queue_length = self.get_queue_length()

        self._queue.update(
            self._queue_task_id,
            description=self.queue_str.format(
                color=self.color, number=queue_length, type_str=self.type_str, title=self.title_lower
            ),
            visible=queue_length > 0,
        )
