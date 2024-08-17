import shutil
import threading
import time

from rich.console import Console

console = Console()
lock=threading.Lock()




class ConsoleManager:
    def __init__(self):
        pass

    @property
    def console(self):
        return console
    

    def log(self,*args, **kwargs):
        thread=threading.Thread(target=self._log_helper,args=args, kwargs=kwargs)
        thread.start()
        thread.join()
    def _log_helper(self,*args, **kwargs):
        _width, _height = shutil.get_terminal_size()
        with lock:
            console.size = (_width, _height - 4)
            self.console.log(*args, **kwargs)
            time.sleep(.4)
            console.size = (_width, _height)
    def print(self,text):
        thread=threading.Thread(self._print_helper,args=text)
        thread.start()
        thread.join()
    def _print_helper(self,text):
        _width, _height = shutil.get_terminal_size()
        with lock:
            console.size = (_width, _height - 4)
            self.console.print(text)
            time.sleep(.3)
            console.size = (_width, _height)
