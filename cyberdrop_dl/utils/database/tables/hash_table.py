from __future__ import annotations
import pathlib
from sqlite3 import IntegrityError

import aiosqlite

from cyberdrop_dl.utils.database.table_definitions import create_hash


class HashTable:
    def __init__(self, db_conn: aiosqlite.Connection):
        self.db_conn: aiosqlite.Connection = db_conn

    async def startup(self) -> None:
        """Startup process for the HistoryTable"""
        await self.db_conn.execute(create_hash)
        await self.db_conn.commit()


    async def get_file_hash_exists(self, full_path):
        """
        Checks if a file exists in the database based on its folder, filename, and size.

        Args:
            full_path: Full path to the file to check.

        Returns:
            hash if  exists
        """

        try:
            # Extract folder, filename, and size from the full path
            path = pathlib.Path(full_path).absolute()
            folder = str(path.parent)
            filename = path.name
            size = path.stat().st_size

            # Connect to the database
            cursor = await self.db_conn.cursor()

            # Check if the file exists with matching folder, filename, and size
            await cursor.execute("SELECT hash FROM hash WHERE folder=? AND filename=? AND size=?", (folder, filename, size))
            result = await cursor.fetchone()
            if result and result[0]:
                return result[0]
            return None
        except Exception as e:
            print(f"Error checking file: {e}")
            return False

    async def get_files_with_hash_matches(self,hash_value,size):
        """
        Retrieves a list of (folder, filename) tuples based on a given hash.

        Args:
            hash_value: The hash value to search for.

        Returns:
            A list of (folder, filename) tuples, or an empty list if no matches found.
        """

        cursor = await self.db_conn.cursor()

        try:
            await cursor.execute("SELECT folder, filename FROM hash WHERE hash = ? and size=?", (hash_value,size))
            results = await cursor.fetchall()
            return results
        except Exception as e:
            print(f"Error retrieving folder and filename: {e}")
            return []
    
   
    async def insert_or_update_hash_db(self, hash_value, file_size, file):
        """
        Inserts or updates a record in the specified SQLite database.

        Args:
            hash_value: The calculated hash of the file.
            file_size: The size of the file in bytes.
            filename: The name of the file.
            folder: The folder containing the file.

        Returns:
            True if the record was inserted or updated successfully, False otherwise.
        """

        cursor = await self.db_conn.cursor()
        full_path=pathlib.Path(file).absolute()
        
        filename=full_path.name
        folder=str(full_path.parent)

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






