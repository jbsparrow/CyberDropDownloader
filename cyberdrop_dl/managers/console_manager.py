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
    

    def log(self,*args, sleep=None,**kwargs):
        self._log_helper(*args,sleep=sleep, **kwargs)
    def _log_helper(self,*args, sleep=None,**kwargs):
        # global _height
        # _width, _new_height = shutil.get_terminal_size()
        # if not _height==_new_height:
        #     _height=_new_height
        #     console.size = (_width, _height - 4)
        self.console.log(*args, **kwargs)
        if sleep:
            time.sleep(sleep)

    def print(self,text,sleep=None):
        self._print_helper(text,sleep=sleep)
    def _print_helper(self,text,sleep=None):
        global _height
        _width, _new_height = shutil.get_terminal_size()
        if not _height==_new_height:
            _height=_new_height
            console.size = (_width, _height - 4)
        self.console.print(text)
        if sleep:
            time.sleep(sleep)
