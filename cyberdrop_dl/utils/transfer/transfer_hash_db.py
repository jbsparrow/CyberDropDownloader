from __future__ import annotations

from pathlib import Path

import arrow
from rich.console import Console

from cyberdrop_dl.utils.database.table_definitions import create_files, create_temp_hash
from cyberdrop_dl.utils.transfer.backup import db_backup
from cyberdrop_dl.utils.transfer.wrapper import db_transfer_context

console = Console()


def transfer_from_old_hash_table(db_path):
    """Transfers data from the old 'hash' table to new 'files' and 'temp_hash' tables, handling potential schema differences and errors.

    Args:
        self: The instance of the class containing this method.

    Raises:
        Exception: If a critical error
    """

    with db_transfer_context(db_path) as cursor:
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
            "INSERT INTO files (folder, download_filename, original_filename, file_size, referer, date) VALUES (?, ?, ?, ?, ?, ?);",
            data_to_insert_files,
        )

        cursor.executemany(
            "INSERT INTO temp_hash (folder, download_filename, hash_type, hash) VALUES (?, ?, ?, ?);",
            data_to_insert_hash,
        )

        # Drop the old 'hash' table
        cursor.execute("DROP TABLE hash")

        # Rename the 'temp_hash' table to 'hash'
        cursor.execute("ALTER TABLE temp_hash RENAME TO hash")
