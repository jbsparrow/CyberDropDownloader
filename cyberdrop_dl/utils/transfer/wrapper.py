import contextlib
import sqlite3


@contextlib.contextmanager
def db_transfer_context(db_file):
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
