from pathlib import Path
from shutil import copy2
def db_backup(db_file):
    while True:
        new_file = Path(f"{db_file}{i}")
        if new_file.exists():
            i = i + 1
            continue
        copy2(db_file, new_file)
        