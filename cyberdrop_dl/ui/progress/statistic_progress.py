from __future__ import annotations

import re
from functools import lru_cache
from typing import NamedTuple

from rich.console import Group
from rich.panel import Panel
from rich.progress import BarColumn, Progress, TaskID

SPLIT_BY_UPPERCASE_REGEX = re.compile(r"[A-Z][a-z]*|[a-z]+|\d+")


class TaskInfo(NamedTuple):
    id: TaskID
    description: str
    completed: float
    total: float | None
    progress: float


class UiFailureTotal(NamedTuple):
    full_msg: str
    count: int
    error_code: int | None
    msg: str

    @classmethod
    def from_pair(cls, full_msg: str, count: int) -> UiFailureTotal:
        parts = full_msg.split(" ", 1)
        if len(parts) > 1 and parts[0].isdigit:
            error_code, msg = parts
            return cls(full_msg, count, int(error_code), msg)
        return cls(full_msg, count, None, full_msg)


def get_tasks_info_sorted(progress: Progress) -> tuple[list[TaskInfo], bool]:
    tasks = [
        TaskInfo(
            id=task.id,
            description=task.description,
            completed=task.completed,
            total=task.total,
            progress=(task.completed / task.total if task.total else 0),
        )
        for task in progress.tasks
    ]

    tasks_sorted = sorted(tasks, key=lambda x: x.completed, reverse=True)
    were_sorted = tasks == tasks_sorted
    return tasks_sorted, were_sorted


class StatsProgress:
    """Base class that keeps track of failures and reasons."""

    title = "Download Failures"

    def __init__(self) -> None:
        self.progress = Progress(
            "[progress.description]{task.description}",
            BarColumn(bar_width=None),
            "[progress.percentage]{task.percentage:>6.2f}%",
            "━",
            "{task.completed:,}",
        )
        self.progress_group = Group(self.progress)
        self.failure_types: dict[str, TaskID] = {}
        self.failed_files = 0
        self.panel = Panel(
            self.progress_group,
            title=self.title,
            border_style="green",
            padding=(1, 1),
            subtitle=self.subtitle,
        )

    @property
    def subtitle(self) -> str:
        return f"Total {self.title}: [white]{self.failed_files}"

    def get_progress(self) -> Panel:
        """Returns the progress bar."""
        return self.panel

    def update_total(self, total: int) -> None:
        """Updates the total number download failures."""
        self.panel.subtitle = self.subtitle
        for key in self.failure_types:
            self.progress.update(self.failure_types[key], total=total)

        tasks_sorted, were_sorted = get_tasks_info_sorted(self.progress)
        if not were_sorted:
            self.sort_tasks(tasks_sorted)

    def sort_tasks(self, tasks_sorted: list[TaskInfo]) -> None:
        for task_id in [task.id for task in tasks_sorted]:
            self.progress.remove_task(task_id)

        for task in tasks_sorted:
            self.failure_types[task.description] = self.progress.add_task(
                task.description,
                total=task.total,
                completed=task.completed,  # type: ignore
            )

    def add_failure(self, failure: str) -> None:
        """Adds a failed file to the progress bar."""
        self.failed_files += 1
        key = prettify_failure(failure)
        task_id = self.failure_types.get(key)
        if task_id is not None:
            self.progress.advance(task_id)
        else:
            self.failure_types[key] = self.progress.add_task(key, total=self.failed_files, completed=1)
        self.update_total(self.failed_files)

    def return_totals(self) -> list[UiFailureTotal]:
        """Returns the total number of failed sites and reasons."""
        failures = {}
        for key, task_id in self.failure_types.items():
            task = next(task for task in self.progress.tasks if task.id == task_id)
            failures[key] = task.completed
        return sorted(UiFailureTotal.from_pair(*f) for f in failures.items())


class DownloadStatsProgress(StatsProgress):
    """Class that keeps track of download failures and reasons."""


class ScrapeStatsProgress(StatsProgress):
    """Class that keeps track of scraping failures and reasons."""

    title = "Scrape Failures"

    def __init__(self) -> None:
        super().__init__()
        self.unsupported_urls = 0
        self.sent_to_jdownloader = 0
        self.unsupported_urls_skipped = 0

    def add_unsupported(self, sent_to_jdownloader: bool = False) -> None:
        """Adds an unsupported url to the progress bar."""
        self.unsupported_urls += 1
        if sent_to_jdownloader:
            self.sent_to_jdownloader += 1
        else:
            self.unsupported_urls_skipped += 1


@lru_cache
def prettify_failure(failure: str) -> str:
    return " ".join(s.capitalize() for s in split_by_uppercase(failure))


def split_by_uppercase(text: str) -> list[str]:
    return re.findall(SPLIT_BY_UPPERCASE_REGEX, text)
