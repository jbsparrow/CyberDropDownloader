from __future__ import annotations
import pathlib
from sqlite3 import Row, IntegrityError

import aiosqlite

from cyberdrop_dl.utils.database.table_definitions import create_hash


class HashTable:
    def __init__(self, db_conn: aiosqlite.Connection):
        self.db_conn: aiosqlite.Connection = db_conn

    async def startup(self) -> None:
        """Startup process for the HistoryTable"""
        await self.db_conn.execute(create_hash)
        await self.db_conn.commit()


    async def check_file_hash_exists(self, full_path):
        """
        Checks if a file exists in the database based on its folder, filename, and size.

        Args:
            db_path: Path to the SQLite database file.
            full_path: Full path to the file to check.

        Returns:
            True if the file exists and has a hash, False otherwise.
        """

        try:
            # Extract folder, filename, and size from the full path
            path = pathlib.Path(full_path)
            folder = str(path.parent)
            filename = path.name
            size = path.stat().st_size

            # Connect to the database
            cursor = await self.db_conn.cursor()

            # Check if the file exists with matching folder, filename, and size
            await cursor.execute("SELECT hash FROM hash WHERE folder=? AND filename=? AND size=?", (folder, filename, size))
            result = await cursor.fetchone()


            return bool(result and result[0])  # Return True if a hash exists, False otherwise
        except Exception as e:
            print(f"Error checking file: {e}")
            return False

    async def insert_or_update_hash_db(self, hash_value, file_size, filename, folder):
        """
        Inserts or updates a record in the specified SQLite database.

        Args:
            db_file: Path to the SQLite database file.
            hash_value: The calculated hash of the file.
            file_size: The size of the file in bytes.
            filename: The name of the file.
            folder: The folder containing the file.

        Returns:
            True if the record was inserted or updated successfully, False otherwise.
        """

        cursor = await self.db_conn.cursor()
        
        filename=str(filename)
        folder=str(folder)

        # Assuming a table named 'file_info' with columns: id (primary key), hash, size, filename, folder
        try:
            await cursor.execute("INSERT INTO hash (hash, size, filename, folder) VALUES (?, ?, ?, ?)",
                        (hash_value, file_size, filename, folder))
            await self.db_conn.commit()
            return True
        except IntegrityError:
            # Handle potential duplicate key (assuming a unique constraint on hash, filename, and folder)
            await cursor.execute("UPDATE hash SET size=?,hash=? WHERE filename=? AND folder=?",
                        (file_size,hash_value, filename, folder))
            await self.db_conn.commit()
            return True
        except Exception as e:
            print(f"Error inserting/updating record: {e}")
            return False






