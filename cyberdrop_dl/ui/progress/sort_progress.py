from __future__ import annotations

from typing import TYPE_CHECKING

from rich.console import Group
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskID

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager


def adjust_title(s: str, length: int = 40, placeholder: str = "...") -> str:
    """Collapse and truncate or pad the given string to fit in the given length."""
    return f"{s[:length - len(placeholder)]}{placeholder}" if len(s) >= length else s.ljust(length)


class SortProgress:
    """Class that keeps track of sorted files."""

    def __init__(self, visible_task_limit: int, manager: Manager) -> None:
        self.manager = manager
        # Sorter to track the progress of folders being sorted, should work similar to the file_progress but for folders, with a percentage and progress bar for the files within the folders
        self.progress = Progress(
            SpinnerColumn(),
            "[progress.description]{task.description}",
            BarColumn(bar_width=None),
            "[progress.percentage]{task.percentage:>6.2f}%",
            "━",
            "{task.completed}/{task.total} files",
        )
        self.overflow = Progress("[progress.description]{task.description}")
        self.queue = Progress("[progress.description]{task.description}")
        self.progress_group = Group(self.progress, self.overflow, self.queue)

        self.color = "plum3"
        self.type_str = "Folders"
        self.progress_str = "[{color}]{description}"
        self.overflow_str = "[{color}]... And {number} Other Folders"
        self.queue_length = 0
        self.queue_str = "[{color}]... And {number} Folders In Sort Queue"
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
        self.tasks_visibility_limit = visible_task_limit
        self.panel = Panel(
            self.progress_group,
            title=f"Sorting Downloads ━ Config: {self.manager.config_manager.loaded_config}",
            border_style="green",
            padding=(1, 1),
        )

        # counts
        self.audio_count = 0
        self.video_count = 0
        self.image_count = 0
        self.other_count = 0

    def get_progress(self) -> Panel:
        """Returns the progress bar."""
        return self.panel

    def set_queue_length(self, length: int) -> None:
        self.queue_length = length

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

        queue_length = self.queue_length
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

    def add_task(self, folder: str, expected_size: int | None) -> TaskID:
        """Adds a new task to the progress bar."""
        # description = f'Sorting {folder}'
        description = folder
        description = description.encode("ascii", "ignore").decode().strip()
        description = adjust_title(description)

        if len(self.visible_tasks) >= self.tasks_visibility_limit:
            task_id = self.progress.add_task(
                self.progress_str.format(color=self.color, description=description),
                total=expected_size,
                visible=False,
            )
            self.invisible_tasks.append(task_id)
        else:
            task_id = self.progress.add_task(
                self.progress_str.format(color=self.color, description=description),
                total=expected_size,
            )
            self.visible_tasks.append(task_id)
        self.redraw()
        return task_id

    def remove_folder(self, task_id: TaskID) -> None:
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

    def advance_folder(self, task_id: TaskID, amount: int) -> None:
        """Advances the progress of the given task by the given amount."""
        if task_id in self.uninitiated_tasks:
            self.uninitiated_tasks.remove(task_id)
            self.invisible_tasks.append(task_id)
            self.redraw()
        self.progress.advance(task_id, amount)

    def increment_audio(self) -> None:
        self.audio_count += 1

    def increment_video(self) -> None:
        self.video_count += 1

    def increment_image(self) -> None:
        self.image_count += 1

    def increment_other(self) -> None:
        self.other_count += 1
