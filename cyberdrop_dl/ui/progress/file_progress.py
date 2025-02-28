from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import ByteSize
from rich.markup import escape
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TimeRemainingColumn,
    TransferSpeedColumn,
)

from cyberdrop_dl.ui.progress.deque_progress import DequeProgress, adjust_title

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager


class FileProgress(DequeProgress):
    """Class that manages the download progress of individual files."""

    def __init__(self, visible_tasks_limit: int, manager: Manager) -> None:
        self.manager = manager
        progress_colums = (SpinnerColumn(), "[progress.description]{task.description}", BarColumn(bar_width=None))
        horizontal_columns = (
            *progress_colums,
            "[progress.percentage]{task.percentage:>6.2f}%",
            "━",
            DownloadColumn(),
            "━",
            TransferSpeedColumn(),
            "━",
            TimeRemainingColumn(),
        )
        vertical_columns = (*progress_colums, DownloadColumn(), "━", TransferSpeedColumn())
        use_columns = horizontal_columns
        if manager.progress_manager.portrait:
            use_columns = vertical_columns
        self._progress = Progress(*use_columns)
        self.downloaded_data = ByteSize(0)
        super().__init__("Downloads", visible_tasks_limit)

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

    def add_task(self, *, domain: str, filename: str, expected_size: int | None = None) -> TaskID:
        """Adds a new task to the progress bar."""
        filename = filename.split("/")[-1].encode("ascii", "ignore").decode().strip()
        # We need a minimum of 30 characters to properly show the download progress + 10 for the bar
        max_size = min((self.manager.progress_manager.console.size.width - 40), 40)
        description = escape(adjust_title(filename, length=max_size))
        if not self.manager.progress_manager.portrait:
            description = f"({domain.upper()}) {description}"
        return super().add_task(description, expected_size)

    def advance_file(self, task_id: TaskID, amount: int) -> None:
        """Advances the progress of the given task by the given amount."""
        self.downloaded_data += amount
        self._progress.advance(task_id, amount)

    def get_speed(self, task_id: TaskID) -> float:
        if task_id not in self._tasks:
            msg = "Task ID not found"
            raise ValueError(msg)

        task = self._progress._tasks[task_id]
        return task.finished_speed or task.speed or 0
