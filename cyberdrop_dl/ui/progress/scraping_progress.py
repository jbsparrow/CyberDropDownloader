from __future__ import annotations

from typing import TYPE_CHECKING

from rich.progress import Progress, SpinnerColumn, TaskID

from cyberdrop_dl.ui.progress.deque_progress import DequeProgress

if TYPE_CHECKING:
    from yarl import URL

    from cyberdrop_dl.managers.manager import Manager


def adjust_title(s: str, length: int = 40, placeholder: str = "...") -> str:
    """Collapse and truncate or pad the given string to fit in the given length."""
    return f"{s[:length - len(placeholder)]}{placeholder}" if len(s) >= length else s.ljust(length)


class ScrapingProgress(DequeProgress):
    """Class that manages the download progress of individual files."""

    def __init__(self, visible_tasks_limit: int, manager: Manager) -> None:
        self.progress = Progress(SpinnerColumn(), "[progress.description]{task.description}")
        self.title = "Scraping"
        self.type_str = "URLs"
        super().__init__(visible_tasks_limit, manager)

    def get_queue_length(self) -> int:
        """Returns the number of tasks in the scraper queue."""
        total = 0
        unique_crawler_ids = set()
        for crawler in self.manager.scrape_mapper.existing_crawlers.values():
            crawler_id = id(crawler)  # Only count each instance of the crawler once
            if crawler_id in unique_crawler_ids:
                continue
            unique_crawler_ids.add(crawler_id)
            total += crawler.waiting_items

        return total

    def redraw(self, passed: bool = False) -> None:
        super().redraw()
        if not passed:
            self.manager.progress_manager.file_progress.redraw(True)

    def add_task(self, url: URL) -> TaskID:
        """Adds a new task to the progress bar."""
        return super().add_task(str(url))
