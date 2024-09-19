from typing import TYPE_CHECKING

from humanfriendly import format_size
from rich.console import Group
from rich.panel import Panel
from rich.progress import Progress, BarColumn

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager


class HashProgress:
    """Class that keeps track of hashed files"""

    def __init__(self, manager: 'Manager'):
        self.manager = manager
        self.hash_progress = Progress("[progress.description]{task.description}",
                                      BarColumn(bar_width=None),
                                      "{task.completed} Files")
        self.remove_progress = Progress("[progress.description]{task.description}",
                                        BarColumn(bar_width=None),
                                        "{task.completed} Files")
        self.match_progress = Progress("[progress.description]{task.description}",
                                       BarColumn(bar_width=None),
                                       "{task.completed} of {task.total} Files")

        self.current_hashing_text = Progress("{task.description}")

        self.hashed_files = 0
        self.prev_hashed_files = 0

        self.hash_progress_group = Group(self.current_hashing_text, self.hash_progress)

        self.hashed_files_task_id = self.hash_progress.add_task("[green]Hashed", total=None)
        self.prev_hashed_files_task_id = self.hash_progress.add_task("[green]Previously Hashed", total=None)

        self.currently_hashing_task_id = self.current_hashing_text.add_task("")

        self.currently_hashing_size_task_id = self.current_hashing_text.add_task("")

        self.removed_files = 0
        self.removed_prev_files = 0
        self.removed_progress_group = Group(self.match_progress, self.remove_progress)
        self.removed_files_task_id = self.remove_progress.add_task("[green]Removed From Currently Downloaded Files",
                                                                   total=None)
        self.removed_prev_files_task_id = self.remove_progress.add_task(
            "[green]Removed From Previously Downloaded Files", total=None)

    async def get_hash_progress(self) -> Panel:
        """Returns the progress bar"""
        return Panel(self.hash_progress_group, title=f"Config: {self.manager.config_manager.loaded_config}",
                     border_style="green", padding=(1, 1))

    async def get_removed_progress(self) -> Panel:
        """Returns the progress bar"""
        return Panel(self.removed_progress_group, border_style="green", padding=(1, 1))

    async def update_currently_hashing(self, file):
        self.current_hashing_text.update(self.currently_hashing_task_id, description=f"[blue]{file}")

        self.current_hashing_text.update(self.currently_hashing_size_task_id,
                                         description=f"[blue]{format_size(file.stat().st_size)}")

    async def add_new_completed_hash(self) -> None:
        """Adds a completed file to the progress bar"""
        self.hash_progress.advance(self.hashed_files_task_id, 1)
        self.hashed_files += 1

    async def add_prev_hash(self) -> None:
        """Adds a completed file to the progress bar"""
        self.hash_progress.advance(self.prev_hashed_files_task_id, 1)
        self.prev_hashed_files += 1

    async def add_removed_file(self) -> None:
        """Adds a completed file to the progress bar"""
        self.remove_progress.advance(self.removed_files_task_id, 1)
        self.removed_files += 1

    async def add_removed_prev_file(self) -> None:
        """Adds a completed file to the progress bar"""
        self.remove_progress.advance(self.removed_prev_files_task_id, 1)
        self.removed_prev_files += 1
