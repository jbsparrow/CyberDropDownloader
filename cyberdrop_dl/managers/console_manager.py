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
    if  level>=LEVEL:
        # QUEUE.append((record,sleep))
        console.log(record)
        if sleep:
            time.sleep(sleep)
def print_(text,sleep=None):
    set_console_height()
    console.print(text)

def set_console_height():
    global _HEIGHT
    _width, _new_height = shutil.get_terminal_size()
    if not _HEIGHT==_new_height:
        _HEIGHT=_new_height
    console.size = (_width, _HEIGHT - 4)

class ConsoleManager:
    def __init__(self): 
        self.thread=None
    
    def startup(self) -> None:
        pass
        # self.thread = threading.Thread(target=self.flush_buffer_thread)
        # self.thread.start()
    def close(self):
        pass
        # if self.thread:
        #     self.thread.join()

    def flush_buffer_thread(self):
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
                set_console_height()
                console.log("\n".join(log_rends))
                if sleep:
                    time.sleep(sleep)
            except Exception:
                pass
   

