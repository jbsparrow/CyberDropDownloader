from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import ByteSize
from rich.console import Group
from rich.panel import Panel
from rich.progress import BarColumn, Progress

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager


class HashProgress:
    """Class that keeps track of hashed files."""

    def __init__(self, manager: Manager) -> None:
        self.manager = manager
        self.hash_progress = self.create_generic_progress()
        self.remove_progress = self.create_generic_progress()
        self.match_progress = self.create_generic_progress()
        self.current_hashing_text = Progress("{task.description}")

        # hashing
        self.hashed_files = self.prev_hashed_files = 0
        self.hash_progress_group = Group(self.current_hashing_text, self.hash_progress)
        self.hashed_files_task_id = self.hash_progress.add_task("[green]Hashed", total=None)
        self.prev_hashed_files_task_id = self.hash_progress.add_task("[green]Previously Hashed", total=None)
        self.currently_hashing_task_id = self.current_hashing_text.add_task("")
        self.currently_hashing_size_task_id = self.current_hashing_text.add_task("")

        # remove
        self.removed_files = 0
        self.removed_progress_group = Group(self.match_progress, self.remove_progress)
        self.removed_files_task_id = self.remove_progress.add_task(
            "[green]Removed From Downloaded Files",
            total=None,
        )

    def create_generic_progress(self) -> Progress:
        return Progress("[progress.description]{task.description}", BarColumn(bar_width=None), "{task.completed:,}")

    def get_renderable(self) -> Panel:
        """Returns the progress bar."""
        return Panel(
            self.hash_progress_group,
            title=f"Config: {self.manager.config_manager.loaded_config}",
            border_style="green",
            padding=(1, 1),
        )

    def get_removed_progress(self) -> Panel:
        """Returns the progress bar."""
        return Panel(self.removed_progress_group, border_style="green", padding=(1, 1))

    def update_currently_hashing(self, file: Path | str) -> None:
        self.current_hashing_text.update(self.currently_hashing_task_id, description=f"[blue]{file}")
        file_size = ByteSize(Path(file).stat().st_size)
        self.current_hashing_text.update(
            self.currently_hashing_size_task_id,
            description=f"[blue]{file_size.human_readable(decimal=True)}",
        )

    def add_new_completed_hash(self) -> None:
        """Adds a completed file to the progress bar."""
        self.hash_progress.advance(self.hashed_files_task_id, 1)
        self.hashed_files += 1

    def add_prev_hash(self) -> None:
        """Adds a completed file to the progress bar."""
        self.hash_progress.advance(self.prev_hashed_files_task_id, 1)
        self.prev_hashed_files += 1

    def add_removed_file(self) -> None:
        """Adds a completed file to the progress bar."""
        self.remove_progress.advance(self.removed_files_task_id, 1)
        self.removed_files += 1

    def reset(self):
        """Resets the progress bar."""
        self.hash_progress.reset(self.hashed_files_task_id)
        self.hash_progress.reset(self.prev_hashed_files_task_id)
        self.hashed_files = self.prev_hashed_files = 0

        self.remove_progress.reset(self.removed_files_task_id)
        self.removed_files = 0
