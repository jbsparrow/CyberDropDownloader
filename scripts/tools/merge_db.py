import logging
import sqlite3

from cyclopts.core import App

from cyberdrop_dl.commands import SQLiteFile
from cyberdrop_dl.logs import setup_console_logging

app = App()
logger = logging.getLogger("cyberdrop_dl.merge_db")


@app.default()
def merge(main_db: SQLiteFile, /, attach_db: SQLiteFile) -> None:
    """Merge rows from `attach_db` into `main_db`

    Only merges rows from `media`, `files` and `hash`

    Both databases MUST have the same schema version
    """
    logger.info("Merging rows from '%s' into '%s'", attach_db, main_db)
    conn = sqlite3.connect(main_db)
    cursor = conn.cursor()

    try:
        cursor.execute("PRAGMA foreign_keys = OFF;")
        cursor.execute('ATTACH DATABASE ? AS "b";', (str(attach_db),))
        with conn:
            for table in ("media", "files", "hash"):
                cursor.execute(f"INSERT OR IGNORE INTO {table} SELECT * FROM b.{table};")  # noqa: S608

        conn.commit()
        cursor.execute("PRAGMA foreign_keys = ON;")
        logger.info("Running 'VACUMM' on main_db ('%s')", main_db)
        conn.execute("VACUUM;")
        logger.info("DONE")
    finally:
        try:
            conn.execute("DETACH DATABASE b;")
        except sqlite3.OperationalError:
            pass
        conn.close()


if __name__ == "__main__":
    with setup_console_logging():
        app()
