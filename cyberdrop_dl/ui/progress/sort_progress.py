from typing import TYPE_CHECKING

from rich.console import Group
from rich.panel import Panel
from rich.progress import Progress, BarColumn
from humanfriendly import format_size

if TYPE_CHECKING:
    from cyberdrop_dl.managers.manager import Manager

class SortProgress:
    """Class that keeps track of sorted files"""

    def __init__(self, manager: 'Manager'):
        self.manager = manager
        self.sort_progress =  Progress("[progress.description]{task.description}",
                                 BarColumn(bar_width=None),
                                 "[progress.percentage]{task.percentage:>3.2f}%",
                                 "{task.completed} of {task.total} Folders")
  
        self.sorted_dirs = 0

        self.sort_progress_group = Group( self.sort_progress)
        self.sorted_dir_task_id = self.sort_progress.add_task("[green]Completed", total=0)
    

    async def set_total(self,total) -> None:
        """sets the total number of directories to be be sorted"""
        self.sort_progress.update(self.sorted_dir_task_id,total=total)


    
    async def get_sort_progress(self) -> Panel:
        """Returns the progress bar"""
        return Panel(self.sort_progress_group, title=f"Config: {self.manager.config_manager.loaded_config}", border_style="green", padding=(1, 1))



    async def add_sorted_dir(self) -> None:
        """Adds a completed dir to the progress bar"""
        self.sort_progress.advance(self.sorted_dir_task_id , 1)
        self.sorted_dirs += 1


