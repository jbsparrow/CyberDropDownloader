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


    async def get_file_hash_exists(self, full_path: Path | str,hash_type:str) -> str | None:
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

            # Connect to the database
            cursor = await self.db_conn.cursor()

            # Check if the file exists with matching folder, filename, and size
            await cursor.execute(
                "SELECT hash FROM hash WHERE folder=? AND original_filename=? AND hash_type=? AND hash IS NOT NULL",
                (folder, filename,hash_type),
            )
            results = await cursor.fetchall()
            if results:
                return results
        except Exception as e:
            console.print(f"Error checking file: {e}")
        return None

    async def get_files_with_hash_matches(self, hash_value: str, size: int,hash_type:str=None) -> list:
        """Retrieves a list of (folder, filename) tuples based on a given hash.

        Args:
            hash_value: The hash value to search for.
            size: file size

        Returns:
            A list of (folder, filename) tuples, or an empty list if no matches found.
        """
        cursor = await self.db_conn.cursor()

        try:
            if hash_type:
                await cursor.execute(
                    "SELECT files.folder, files.download_filename FROM hash JOIN files ON hash.folder = files.folder AND hash.original_filename = files.original_filename WHERE hash.hash = ? AND files.file_size = ? AND hash.hash_type = ?;",
                    (hash_value, size,hash_type),
                )
                return await cursor.fetchall()
            else:
                await cursor.execute(
                    "SELECT files.folder, files.download_filename FROM hash JOIN files ON hash.folder = files.folder AND hash.original_filename = files.original_filename WHERE hash.hash = ? AND files.file_size = ? AND hash.hash_type = ?;",
                    (hash_value, size,hash_type),
                )
                return await cursor.fetchall()

        except Exception as e:
            console.print(f"Error retrieving folder and filename: {e}")
            return []

    async def insert_or_update_hash_db(self, hash_value: str,hash_type:str, file: str, original_filename: str, referer: URL) -> bool:
        """Inserts or updates a record in the specified SQLite database.

        Args:
            hash_value: The calculated hash of the file.
            file: The file path
            original_filename: The name original name of the file.
            referer: referer URL
            hash_type: The hash type (e.g., md5, sha256)

        Returns:
            True if all the record was inserted or updated successfully, False otherwise.
        """
        referer = str(referer)
        full_path = Path(file).absolute()
        file_size = full_path.stat().st_size

        download_filename = full_path.name
        original_filename = referer or download_filename
        folder = str(full_path.parent)
        hash=await self.insert_or_update_hashes(hash_value,hash_type,folder, original_filename)
        file=await self.insert_or_update_file(folder, original_filename,download_filename,file_size,referer)
        return file and hash

    async def insert_or_update_hashes(self,hash_value,hash_type,folder, original_filename):
        cursor = await self.db_conn.cursor()
        try:
            await cursor.execute(
                "INSERT INTO hash (hash,hash_type,folder,original_filename) VALUES (?, ?, ?, ?)",
                (hash_value,hash_type,folder, original_filename),
            )
            await self.db_conn.commit()
        except IntegrityError as _:
            # Handle potential duplicate key (assuming a unique constraint on (folder, original_filename, hash_type)
            await cursor.execute(
                """UPDATE hash
                SET hash = ?
                WHERE original_filename = ? AND folder = ? AND hash_type = ?;""",
                (
                    hash_value,
                    original_filename,
                    folder,
                    hash_type,
                ),
            )
            await self.db_conn.commit()
        except Exception as e:
            console.print(f"Error inserting/updating record: {e}")
            return False
        return True
    async def insert_or_update_file(self,folder, original_filename,download_filename,file_size,referer):
        cursor = await self.db_conn.cursor()
        try:
            await cursor.execute(
                "INSERT INTO files (folder,original_filename,download_filename,file_size,referer) VALUES (?, ?, ?, ?,?)",
                (folder, original_filename,download_filename,file_size,referer),
            )
            await self.db_conn.commit()
        except IntegrityError as _:
            # Handle potential duplicate key (assuming a unique constraint on  (filename, and folder)
            await cursor.execute(
    """UPDATE files
    SET download_filename = ?, file_size = ?, referer = ?
    WHERE original_filename = ? AND folder = ?;""",
    (
        download_filename,
        file_size,
        referer,
        original_filename,
        folder,
    ),
)

            await self.db_conn.commit()
        except Exception as e:
            console.print(f"Error inserting/updating record: {e}")
            return False
        return True

    async def get_all_unique_hashes(self,hash_type=None) -> list:
        """Retrieves a list of hashes

        Args:
            hash_value: The hash value to search for.
            hash_type: The type of hash[optional]

        Returns:
            A list of (folder, filename) tuples, or an empty list if no matches found.
        """
        cursor = await self.db_conn.cursor()
        try:
            if hash_type:
                await cursor.execute(
                    "SELECT DISTINCT hash FROM hash WHERE hash_type =?",
                    (hash_type,),
                )
            else:
                await cursor.execute("SELECT DISTINCT hash FROM hash")
            results = await cursor.fetchall()
            return [x[0] for x in results]
        except Exception as e:
            console.print(f"Error retrieving folder and filename: {e}")
            return []
