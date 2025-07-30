from __future__ import annotations

from typing import TYPE_CHECKING

from rich.progress import Progress, SpinnerColumn, TaskID

from cyberdrop_dl.ui.progress.deque_progress import DequeProgress

if TYPE_CHECKING:
    from yarl import URL

    from cyberdrop_dl.managers.manager import Manager


class ScrapingProgress(DequeProgress):
    """Class that manages the download progress of individual files."""

    type_str = "URLs"

    def __init__(self, manager: Manager) -> None:
        self.manager = manager
        self._progress = Progress(SpinnerColumn(), "[progress.description]{task.description}")
        visible_tasks_limit: int = manager.config_manager.global_settings_data.ui_options.scraping_item_limit
        super().__init__("Scraping", visible_tasks_limit)

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
            self.manager.progress_manager.file_progress.redraw()

    def add_task(self, url: URL) -> TaskID:  # type: ignore[reportIncompatibleMethodOverride]
        """Adds a new task to the progress bar."""
        return super().add_task(str(url))
