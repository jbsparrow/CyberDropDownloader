import shutil
import threading
import time

from rich.console import Console

console = Console()
_height,_width=None,None



class ConsoleManager:
    def __init__(self):
        pass
    


    @property
    def console(self):
        return console
    

    def log(self,*args, **kwargs):
        self._log_helper(*args, **kwargs)
    def _log_helper(self,*args, **kwargs):
        global _height
        _width, _new_height = shutil.get_terminal_size()
        if not _height==_new_height:
            _height=_new_height
            console.size = (_width, _height - 4)
        self.console.log(*args, **kwargs)
    def print(self,text):
        self._print_helper(text)
    def _print_helper(self,text):
        global _height
        _width, _new_height = shutil.get_terminal_size()
        if not _height==_new_height:
            _height=_new_height
            console.size = (_width, _height - 4)
        self.console.print(text)
