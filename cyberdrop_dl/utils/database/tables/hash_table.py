from __future__ import annotations

from pathlib import Path
from sqlite3 import IntegrityError
from typing import TYPE_CHECKING

from rich.console import Console

from cyberdrop_dl.utils.database.table_definitions import create_hash,create_temp_hash,create_files

if TYPE_CHECKING:
    import aiosqlite
    from yarl import URL

console = Console()


class HashTable:
    def __init__(self, db_conn: aiosqlite.Connection) -> None:
        self.db_conn: aiosqlite.Connection = db_conn

    async def startup(self) -> None:
        """Startup process for the HistoryTable."""
        await self.transer_old_hash_table()
        await self.create_hash_tables()
        pass


    async def create_hash_tables(self):
        await self.db_conn.execute(create_files)
        await self.db_conn.execute(create_hash)
        await self.db_conn.commit()


    async def transer_old_hash_table(self):
        cursor = await self.db_conn.cursor()
        results = await cursor.execute("""pragma table_info(hash)""")
        results = await results.fetchall()
        if  len(list(filter(lambda x: x[1]=="download_filename",results)))>0:
            await cursor.execute(create_files)
            await cursor.execute(create_temp_hash)
            old_table_results=await cursor.execute(
                "SELECT * FROM hash" ,
                (),
            )
            for  old_result in await old_table_results.fetchall():
                folder=old_result[0]
                dl_name=old_result[1]
                original_filename=old_result[2]
                size=old_result[3]
                hash=old_result[4]
                referer=old_result[5]
                hash_type="md5"
                await cursor.execute(
                    "INSERT OR IGNORE INTO files (folder, download_filename, original_filename, file_size,  referer) VALUES (?,?,?,?,?);",
                    (folder, dl_name, original_filename, size,   referer),
                )
                await cursor.execute(
                    "INSERT OR IGNORE INTO temp_hash (folder, original_filename, hash_type, hash) VALUES (?,?,?,?);",
                    (folder, original_filename,  hash_type,hash),
                )
            await cursor.execute("""DROP TABLE IF EXISTS hash""")
            await cursor.execute("ALTER TABLE temp_hash RENAME TO hash")
            await self.db_conn.commit()


    async def get_file_hash_exists(self, full_path: Path | str) -> str | None:
        """Checks if a file exists in the database based on its folder, filename, and size.

        Args:
            full_path: Full path to the file to check.

        Returns:
            hash if  exists
        """
        try:
            # Extract folder, filename, and size from the full path
            path = Path(full_path).absolute()
            folder = str(path.parent)
            filename = path.name
            size = path.stat().st_size

            # Connect to the database
            cursor = await self.db_conn.cursor()

            # Check if the file exists with matching folder, filename, and size
            await cursor.execute(
                "SELECT hash FROM hash WHERE folder=? AND download_filename=? AND file_size=?",
                (folder, filename, size),
            )
            result = await cursor.fetchone()
            if result and result[0]:
                return result[0]
        except Exception as e:
            console.print(f"Error checking file: {e}")
        return None

    async def get_files_with_hash_matches(self, hash_value: str, size: int) -> list:
        """Retrieves a list of (folder, filename) tuples based on a given hash.

        Args:
            hash_value: The hash value to search for.
            size: file size

        Returns:
            A list of (folder, filename) tuples, or an empty list if no matches found.
        """
        cursor = await self.db_conn.cursor()

        try:
            await cursor.execute(
                "SELECT folder, download_filename FROM hash WHERE hash = ? and file_size=?",
                (hash_value, size),
            )
            return await cursor.fetchall()
        except Exception as e:
            console.print(f"Error retrieving folder and filename: {e}")
            return []

    async def insert_or_update_hash_db(self, hash_value: str, file: str, original_filename: str, referer: URL) -> bool:
        """Inserts or updates a record in the specified SQLite database.

        Args:
            hash_value: The calculated hash of the file.
            file: The file path
            original_filename: The name original name of the file.
            referer: referer URL

        Returns:
            True if the record was inserted or updated successfully, False otherwise.
        """
        referer = str(referer)
        cursor = await self.db_conn.cursor()
        full_path = Path(file).absolute()
        file_size = full_path.stat().st_size

        download_filename = full_path.name
        original_filename = referer or download_filename
        folder = str(full_path.parent)

        # Assuming a table named 'file_info' with columns: id (primary key), hash, size, filename, folder
        try:
            await cursor.execute(
                "INSERT INTO hash (hash, file_size, download_filename, folder,original_filename,referer) VALUES (?, ?, ?, ?,?,?)",
                (hash_value, file_size, download_filename, folder, original_filename, referer),
            )
            await self.db_conn.commit()
        except IntegrityError as _:
            # Handle potential duplicate key (assuming a unique constraint on hash, filename, and folder)
            await cursor.execute(
                """UPDATE hash
    SET file_size = ?,
    hash = ?,
    referer= CASE WHEN ? IS NOT NULL THEN ? ELSE referer END,
    original_filename = CASE WHEN ? IS NOT NULL THEN ? ELSE original_filename END
WHERE download_filename = ? AND folder = ?;""",
                (
                    file_size,
                    hash_value,
                    referer,
                    referer,
                    original_filename,
                    original_filename,
                    download_filename,
                    folder,
                ),
            )
            await self.db_conn.commit()
        except Exception as e:
            console.print(f"Error inserting/updating record: {e}")
            return False
        return True

    async def get_all_unique_hashes(self) -> list:
        """Retrieves a list of (folder, filename) tuples based on a given hash.

        Args:
            hash_value: The hash value to search for.

        Returns:
            A list of (folder, filename) tuples, or an empty list if no matches found.
        """
        cursor = await self.db_conn.cursor()

        try:
            await cursor.execute("SELECT DISTINCT hash FROM hash")
            results = await cursor.fetchall()
            return [x[0] for x in results]
        except Exception as e:
            console.print(f"Error retrieving folder and filename: {e}")
            return []
