import contextlib
import sqlite3
from pathlib import Path
from shutil import copy2
@contextlib.contextmanager
def db_transfer_context(db_file):
    i=2
    while True:
        new_file=Path(f"{db_file}i")
        if new_file.exists():
            i=i+1
            continue

        copy2(db_file,new_file)
        break
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    try:
        yield cursor
        conn.commit()  # commit changes if no exception occurs
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cursor.close()
        conn.close()