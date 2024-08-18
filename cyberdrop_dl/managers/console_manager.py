import shutil
import threading
import time
from collections import deque

from rich.console import Console

console = Console()
_HEIGHT,_=None,None
LEVEL=100
QUEUE= deque()


def log(level,record,*args, sleep=None,**kwargs):
    level=level  or 10
    _log_helper(level,record,sleep=sleep, **kwargs)
def _log_helper(level,record,*args, sleep=None,**kwargs):
    QUEUE.append((record,sleep))

def print_(text,sleep=None):
    _print_helper(text,sleep=sleep)
def _print_helper(text,sleep=None):
    console.print(text)
    

class ConsoleManager:
    def __init__(self):
        
        self.thread=None
    
    def startup(self) -> None:
        self.thread = threading.Thread(target=self.flush_buffer_thread)
        self.thread.start()
    def close(self):
        if self.thread:
            self.thread.join()


    async def flush_buffer_thread(self):
        max_entries=10
        while True:
            log_rends = []
            try:
                num = min(len(QUEUE), max_entries)
                sleep=None
                for _ in range(num):
                    log_renderable,sleep = QUEUE.popleft()
                    log_rends.append(log_renderable)
                    if sleep:
                        break
                if not bool(log_rends):
                    time.sleep(.3)
                    continue
                global _HEIGHT
                _width, _new_height = shutil.get_terminal_size()
                if not _HEIGHT==_new_height:
                    _HEIGHT=_new_height
                console.size = (_width, _HEIGHT - 4)
                console.log("\n".join(log_rends))
                if sleep:
                    time.sleep(sleep)
            except Exception as e:
                pass
   