from __future__ import annotations

from typing import TYPE_CHECKING

from rich.markup import escape
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskID

from cyberdrop_dl.ui.progress.deque_progress import DequeProgress, adjust_title

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager


class SortProgress(DequeProgress):
    """Class that keeps track of sorted files."""

    type_str = "Folders"

    def __init__(self, visible_tasks_limit: int, manager: Manager) -> None:
        """Sorter to track the progress of folders being sorted.

        Should work similar to the file_progress but for folders, with a percentage and progress bar for the files within the folders"""
        self.manager = manager
        self._progress = Progress(
            SpinnerColumn(),
            "[progress.description]{task.description}",
            BarColumn(bar_width=None),
            "[progress.percentage]{task.percentage:>6.2f}%",
            "━",
            "{task.completed}/{task.total} files",
        )
        super().__init__("Sort", visible_tasks_limit)

        # counts
        self.queue_length = self.audio_count = self.video_count = self.image_count = self.other_count = 0

    def get_queue_length(self) -> int:
        return self.queue_length

    def get_renderable(self) -> Panel:
        """Returns the progress bar."""
        return Panel(
            self._progress_group,
            title=f"Sorting Downloads ━ Config: {self.manager.config_manager.loaded_config}",
            border_style="green",
            padding=(1, 1),
        )

    def set_queue_length(self, length: int) -> None:
        self.queue_length = length

    def add_task(self, folder: str, expected_size: int | None) -> TaskID:
        """Adds a new task to the progress bar."""
        # description = f'Sorting {folder}'
        description = folder.encode("ascii", "ignore").decode().strip()
        description = escape(adjust_title(description))
        return super().add_task(description, expected_size)

    def advance_folder(self, task_id: TaskID, amount: int = 1) -> None:
        """Advances the progress of the given task by the given amount."""
        self._progress.advance(task_id, amount)

    def increment_audio(self) -> None:
        self.audio_count += 1

    def increment_video(self) -> None:
        self.video_count += 1

    def increment_image(self) -> None:
        self.image_count += 1

    def increment_other(self) -> None:
        self.other_count += 1
