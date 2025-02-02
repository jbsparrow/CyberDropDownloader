from __future__ import annotations

import contextlib
import sqlite3
from datetime import datetime
from pathlib import Path
from shutil import copy2

import arrow
from rich.console import Console

from cyberdrop_dl.utils.database.table_definitions import create_files, create_temp_hash

console = Console()


def transfer_v5_db_to_v6(db_path: Path) -> None:
    """Transfers data from the old 'hash' table to new 'files' and 'temp_hash' tables, handling potential schema differences and errors.

    Args:
        self: The instance of the class containing this method.

    Raises:
        Exception: If a critical error
    """
    if not db_path.is_file():
        return
    with db_transfer_context(db_path) as cursor:
        # Check if the 'hash' table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='hash'")
        hash_table_exists = cursor.fetchone() is not None

        if not hash_table_exists:
            console.print("[bold yellow]Old 'hash' table not found. Skipping transfer.[/]")
            return

        # Check if the 'hash_type' column exists in the 'hash' table
        cursor.execute("SELECT COUNT(*) FROM pragma_table_info('hash') WHERE name='hash_type'")
        has_hash_type_column = (cursor.fetchone())[0] > 0
        if has_hash_type_column:
            return
        db_backup(db_path)

        # Fetch data from the old 'hash' table
        cursor.execute("""
        SELECT folder, download_filename, file_size, hash, original_filename, referer
            FROM hash
        """)
        old_hash_data = cursor.fetchall()
        # Drop existing 'files' and 'temp_hash' tables if they exist
        cursor.execute("DROP TABLE IF EXISTS files")
        cursor.execute("DROP TABLE IF EXISTS temp_hash")

        # Create the 'temp_hash' table with the required schema
        cursor.execute(create_temp_hash)
        cursor.execute(create_files)

        # Prepare data for insertion into 'files' and 'temp_hash' tables
        data_to_insert_files = []
        data_to_insert_hash = []
        for row in old_hash_data:
            folder, download_filename, file_size, hash, original_filename, referer = row

            file_path = Path(folder, download_filename)
            if file_path.exists():
                file_date = int(file_path.stat().st_mtime)
            else:
                file_date = int(arrow.now().float_timestamp)

            data_to_insert_files.append((folder, download_filename, original_filename, file_size, referer, file_date))
            data_to_insert_hash.append((folder, download_filename, "md5", hash))

        # Insert data into 'files' and 'temp_hash' tables
        cursor.executemany(
            "INSERT OR IGNORE INTO files (folder, download_filename, original_filename, file_size, referer, date) VALUES (?, ?, ?, ?, ?, ?);",
            data_to_insert_files,
        )

        cursor.executemany(
            "INSERT OR IGNORE INTO temp_hash (folder, download_filename, hash_type, hash) VALUES (?, ?, ?, ?);",
            data_to_insert_hash,
        )

        # Drop the old 'hash' table
        cursor.execute("DROP TABLE hash")

        # Rename the 'temp_hash' table to 'hash'
        cursor.execute("ALTER TABLE temp_hash RENAME TO hash")


def db_backup(db_file: Path) -> None:
    new_file = Path(db_file.parent, f"cyberdrop_v5_{datetime.now().strftime('%Y%m%d_%H%M%S')}.bak.db")
    copy2(db_file, new_file)


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
