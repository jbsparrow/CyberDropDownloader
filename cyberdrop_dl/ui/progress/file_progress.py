from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING

from pydantic import ByteSize
from rich.console import Group
from rich.markup import escape
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TimeRemainingColumn,
    TransferSpeedColumn,
)

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager


def adjust_title(s: str, length: int = 40, placeholder: str = "...") -> str:
    """Collapse and truncate or pad the given string to fit in the given length."""
    return f"{s[:length - len(placeholder)]}{placeholder}" if len(s) >= length else s.ljust(length)


class FileProgress:
    """Class that manages the download progress of individual files."""

    def __init__(self, visible_tasks_limit: int, manager: Manager) -> None:
        self.manager = manager

        self.progress = Progress(
            SpinnerColumn(),
            "[progress.description]{task.description}",
            BarColumn(bar_width=None),
            "[progress.percentage]{task.percentage:>6.2f}%",
            "━",
            DownloadColumn(),
            "━",
            TransferSpeedColumn(),
            "━",
            TimeRemainingColumn(),
        )
        self.overflow = Progress("[progress.description]{task.description}")
        self.queue = Progress("[progress.description]{task.description}")
        self.progress_group = Group(self.progress, self.overflow, self.queue)

        self.color = "plum3"
        self.type_str = "Files"
        self.progress_str = "[{color}]{description}"
        self.overflow_str = "[{color}]... And {number} Other {type_str}"
        self.queue_str = "[{color}]... And {number} {type_str} In Download Queue"
        self.overflow_task_id = self.overflow.add_task(
            self.overflow_str.format(color=self.color, number=0, type_str=self.type_str),
            visible=False,
        )
        self.queue_task_id = self.queue.add_task(
            self.queue_str.format(color=self.color, number=0, type_str=self.type_str),
            visible=False,
        )

        self.tasks = deque[TaskID] = deque([])
        self._tasks_visibility_limit = visible_tasks_limit
        self.downloaded_data = ByteSize(0)

    @property
    def visible_tasks(self) -> list[TaskID]:
        return self.tasks[: self._tasks_visibility_limit]

    @property
    def invisible_tasks(self) -> list[TaskID]:
        return self.tasks[-self._tasks_visibility_limit :]

    def get_progress(self) -> Panel:
        """Returns the progress bar."""
        return Panel(self.progress_group, title="Downloads", border_style="green", padding=(1, 1))

    def get_queue_length(self) -> int:
        """Returns the number of tasks in the downloader queue."""
        total = 0
        unique_crawler_ids = set()
        for crawler in self.manager.scrape_mapper.existing_crawlers.values():
            crawler_id = id(crawler)  # Only count each instance of the crawler once
            if crawler_id in unique_crawler_ids:
                continue
            unique_crawler_ids.add(crawler_id)
            total += getattr(crawler.downloader, "waiting_items", 0)

        return total

    def redraw(self) -> None:
        """Redraws the progress bar."""
        self.overflow.update(
            self.overflow_task_id,
            description=self.overflow_str.format(
                color=self.color,
                number=len(self.invisible_tasks),
                type_str=self.type_str,
            ),
            visible=len(self.invisible_tasks) > 0,
        )

        queue_length = self.get_queue_length()

        self.queue.update(
            self.queue_task_id,
            description=self.queue_str.format(color=self.color, number=queue_length, type_str=self.type_str),
            visible=queue_length > 0,
        )

    def add_task(self, *, domain: str, filename: str, expected_size: int | None = None) -> TaskID:
        """Adds a new task to the progress bar."""
        filename = filename.split("/")[-1].encode("ascii", "ignore").decode().strip()
        filename = escape(adjust_title(filename))
        description = f"({domain.upper()}) {filename}"
        show_task = len(self.visible_tasks) < self._tasks_visibility_limit
        task_id = self.progress.add_task(
            self.progress_str.format(color=self.color, description=description),
            total=expected_size,
            visible=show_task,
        )
        self.tasks.append(task_id)
        self.redraw()
        return task_id

    def remove_task(self, task_id: TaskID) -> None:
        """Removes the given task from the progress bar."""
        old_visible_taks = set(self.visible_tasks)
        if task_id not in self.tasks:
            msg = "Task ID not found"
            raise ValueError(msg)

        self.tasks.remove(task_id)
        self.progress.remove_task(task_id)
        new_visible_taks = old_visible_taks - set(self.visible_tasks)
        for task in new_visible_taks:
            self.progress.update(task, visible=True)
        self.redraw()

    def advance_file(self, task_id: TaskID, amount: int) -> None:
        """Advances the progress of the given task by the given amount."""
        self.downloaded_data += amount
        self.progress.advance(task_id, amount)
