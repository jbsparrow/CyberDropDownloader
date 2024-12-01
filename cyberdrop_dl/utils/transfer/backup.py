from datetime import datetime
from pathlib import Path
from shutil import copy2


def db_backup(db_file):
    new_file = Path(db_file.parent, f"cyberdrop_v5_{datetime.now().strftime('%Y%m%d_%H%M%S')}.bak.db")
    copy2(db_file, new_file)
