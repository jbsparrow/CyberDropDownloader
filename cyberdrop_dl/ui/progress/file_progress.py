from __future__ import annotations

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

        self.visible_tasks: list[TaskID] = []
        self.invisible_tasks: list[TaskID] = []
        self.completed_tasks: list[TaskID] = []
        self.uninitiated_tasks: list[TaskID] = []
        self.tasks_visibility_limit = visible_tasks_limit
        self.downloaded_data = ByteSize(0)

    def get_progress(self) -> Panel:
        """Returns the progress bar."""
        return Panel(self.progress_group, title="Downloads", border_style="green", padding=(1, 1))

    def get_download_queue_length(self) -> int:
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

    def redraw(self, passed: bool = False) -> None:
        """Redraws the progress bar."""
        while len(self.visible_tasks) > self.tasks_visibility_limit:
            task_id = self.visible_tasks.pop(0)
            self.invisible_tasks.append(task_id)
            self.progress.update(task_id, visible=False)
        while len(self.invisible_tasks) > 0 and len(self.visible_tasks) < self.tasks_visibility_limit:
            task_id = self.invisible_tasks.pop(0)
            self.visible_tasks.append(task_id)
            self.progress.update(task_id, visible=True)

        if len(self.invisible_tasks) > 0:
            self.overflow.update(
                self.overflow_task_id,
                description=self.overflow_str.format(
                    color=self.color,
                    number=len(self.invisible_tasks),
                    type_str=self.type_str,
                ),
                visible=True,
            )
        else:
            self.overflow.update(self.overflow_task_id, visible=False)

        queue_length = self.get_download_queue_length()
        if queue_length > 0:
            self.queue.update(
                self.queue_task_id,
                description=self.queue_str.format(color=self.color, number=queue_length, type_str=self.type_str),
                visible=True,
            )
        else:
            self.queue.update(self.queue_task_id, visible=False)

        if not passed:
            self.manager.progress_manager.scraping_progress.redraw(True)

    def add_task(self, *, domain: str, filename: str, expected_size: int | None = None) -> TaskID:
        """Adds a new task to the progress bar."""
        filename = filename.split("/")[-1].encode("ascii", "ignore").decode().strip()
        filename = escape(adjust_title(filename))
        description = f"({domain.upper()}) {filename}"
        show_task = len(self.visible_tasks) < self.tasks_visibility_limit
        task_id = self.progress.add_task(
            self.progress_str.format(color=self.color, description=description),
            total=expected_size,
            visible=show_task,
        )

        if show_task:
            self.visible_tasks.append(task_id)
        else:
            self.invisible_tasks.append(task_id)
        self.redraw()
        return task_id

    def remove_file(self, task_id: TaskID) -> None:
        """Removes the given task from the progress bar."""
        if task_id in self.visible_tasks:
            self.visible_tasks.remove(task_id)
            self.progress.update(task_id, visible=False)
        elif task_id in self.invisible_tasks:
            self.invisible_tasks.remove(task_id)
        elif task_id == self.overflow_task_id:
            self.overflow.update(task_id, visible=False)
        else:
            msg = "Task ID not found"
            raise ValueError(msg)
        self.redraw()

    def advance_file(self, task_id: TaskID, amount: int) -> None:
        """Advances the progress of the given task by the given amount."""
        self.downloaded_data += amount
        if task_id in self.uninitiated_tasks:
            self.uninitiated_tasks.remove(task_id)
            self.invisible_tasks.append(task_id)
            self.redraw()
        self.progress.advance(task_id, amount)
