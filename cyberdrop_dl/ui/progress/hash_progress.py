from __future__ import annotations

import contextlib
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import ByteSize
from rich.console import Group
from rich.markup import escape
from rich.panel import Panel
from rich.progress import BarColumn, Progress, TaskID

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager


def _generic_progress() -> Progress:
    return Progress("[progress.description]{task.description}", BarColumn(bar_width=None), "{task.completed:,}")


class HashProgress:
    """Class that keeps track of hashed files."""

    def __init__(self, manager: Manager) -> None:
        self.manager = manager
        self._hash_progress = _generic_progress()
        self._remove_progress = _generic_progress()
        self._match_progress = _generic_progress()
        self._file_info = Progress("{task.description}")
        self._base_dir: Path | None = None

        # hashing
        self._computed_hashes = self._prev_hashed = 0
        self.hash_progress_group = Group(self._file_info, self._hash_progress)

        self._tasks: dict[str, TaskID] = {}

        def add_hashed_task(hash_type: str) -> None:
            desc = "[green]Hashed " + escape(f"[{hash_type}]")
            self._tasks[hash_type] = self._hash_progress.add_task(desc, total=None)

        add_hashed_task("xxh128")
        if manager.config.dupe_cleanup_options.add_md5_hash:
            add_hashed_task("md5")
        if manager.config.dupe_cleanup_options.add_sha256_hash:
            add_hashed_task("sha256")

        self.prev_hashed_files_task_id = self._hash_progress.add_task("[green]Previously Hashed", total=None)

        self._base_dir_task_id = self._file_info.add_task("")
        self._file_task_id = self._file_info.add_task("")

        # remove
        self.removed_files = 0
        self.removed_progress_group = Group(self._match_progress, self._remove_progress)
        self.removed_files_task_id = self._remove_progress.add_task(
            "[green]Removed From Downloaded Files",
            total=None,
        )

    @property
    def hashed_files(self) -> int:
        return int(self._computed_hashes / len(self._tasks))

    @property
    def prev_hashed_files(self) -> int:
        return int(self._prev_hashed / len(self._tasks))

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

    @contextlib.contextmanager
    def currently_hashing_dir(self, path: Path):
        self._base_dir = path
        desc = "[green]Base dir: [blue]" + escape(f"{self._base_dir}")
        self._file_info.update(self._base_dir_task_id, description=desc)
        try:
            yield
        finally:
            self._base_dir = None
            self._file_info.update(self._base_dir_task_id, description="")

    def update_currently_hashing(self, file: Path) -> None:
        if not self._base_dir:
            return
        file_size = ByteSize(Path(file).stat().st_size)
        size_text = file_size.human_readable(decimal=True)
        path = file.relative_to(self._base_dir)
        desc = "[green]Current file: [blue]" + escape(f"{path}") + f" [green]({size_text})"
        self._file_info.update(self._file_task_id, description=desc)

    def add_new_completed_hash(self, hash_type: str) -> None:
        """Adds a completed file to the progress bar."""
        self._hash_progress.advance(self._tasks[hash_type], 1)
        self._computed_hashes += 1

    def add_prev_hash(self) -> None:
        """Adds a completed file to the progress bar."""
        self._hash_progress.advance(self.prev_hashed_files_task_id, 1)
        self._prev_hashed += 1

    def add_removed_file(self) -> None:
        """Adds a removed file to the progress bar."""
        self._remove_progress.advance(self.removed_files_task_id, 1)
        self.removed_files += 1

    def reset(self):
        """Resets the progress bar."""
        for task in self._tasks.values():
            self._hash_progress.reset(task)
        self._hash_progress.reset(self.prev_hashed_files_task_id)
        self._computed_hashes = self._prev_hashed = 0

        self._remove_progress.reset(self.removed_files_task_id)
        self.removed_files = 0
