from typing import Tuple, TYPE_CHECKING

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
        self.remove_progress=Progress("[progress.description]{task.description}",
                                 BarColumn(bar_width=None),
                                 "{task.completed} Files")
        self.match_progress=Progress("[progress.description]{task.description}",
                                 BarColumn(bar_width=None),
                                 "{task.completed} of {task.total} Files")

       
        
        self.hashed_files = 0
        self.prev_hash_files = 0
        self.hash_progress_group = Group(self.hash_progress)
        self.hashed_files_task_id = self.hash_progress.add_task("[green]Hashed", total=None)
        self.prev_hashed_files_task_id = self.hash_progress.add_task("[green]Previously Hashed", total=None)


        self.removed_files=0
        self.removed_progress_group = Group(self.match_progress,self.remove_progress)
        self.removed_files_task_id = self.remove_progress.add_task("[green]Removed Files", total=None)



    async def get_hash_progress(self) -> Panel:
        """Returns the progress bar"""
        return Panel(self.hash_progress_group, title=f"Config: {self.manager.config_manager.loaded_config}", border_style="green", padding=(1, 1))


    async def get_removed_progress(self) -> Panel:
        """Returns the progress bar"""
        return Panel(self.removed_progress_group, border_style="green", padding=(1, 1))

    # async def update_hash(self) -> None:
    #     """Updates the total number of files to be downloaded"""
    #     self.hashed_file_total = self.hashed_file_total  + 1
    #     self.progress.update(self.completed_files_task_id, total=self.hashed_file_total)
      

    async def add_completed_hash(self) -> None:
        """Adds a completed file to the progress bar"""
        self.hash_progress.advance(self.hashed_files_task_id , 1)
        self.hashed_files += 1

    async def add_prev_hash(self) -> None:
        """Adds a completed file to the progress bar"""
        self.hash_progress.advance(self.prev_hashed_files_task_id , 1)
        self.prev_hash_files += 1


    async def add_removed_file(self) -> None:
        """Adds a completed file to the progress bar"""
        self.remove_progress.advance(self.removed_files_task_id , 1)
        self.removed_files += 1

