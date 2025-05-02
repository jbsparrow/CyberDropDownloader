from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, cast

from rich.console import Console

from cyberdrop_dl.utils.database.table_definitions import create_files, create_hash
from cyberdrop_dl.utils.logger import log

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence
    from pathlib import Path

    import aiosqlite
    from yarl import URL

    from cyberdrop_dl.utils.constants import HashType

console = Console()


class HashTable:
    def __init__(self, db_conn: aiosqlite.Connection) -> None:
        self.db_conn: aiosqlite.Connection = db_conn

    async def startup(self) -> None:
        """Startup process for the HistoryTable."""
        await self.create_hash_tables()

    async def create_hash_tables(self) -> None:
        await self.db_conn.execute(create_files)
        await self.db_conn.execute(create_hash)
        await self.db_conn.commit()

    async def get_file_hash_exists(self, full_path: Path, hash_type: HashType) -> str | None:
        """gets the hash from a complete file path

        Args:
            full_path: Full path to the file to check.

        Returns:
            hash if exists
        """
        try:
            # Extract folder, filename, and size from the full pathg
            path = full_path.absolute()
            folder = str(path.parent)
            filename = path.name

            # Connect to the database
            cursor = await self.db_conn.cursor()

            # Check if the file exists with matching folder, filename, and size
            await cursor.execute(
                "SELECT hash FROM hash WHERE folder=? AND download_filename=? AND hash_type=? AND hash IS NOT NULL",
                (folder, filename, hash_type),
            )
            result = await cursor.fetchone()
            if result:
                return result[0]
        except Exception as e:
            log(f"Error checking file: {e}", 40)
        return None

    async def get_files_with_hash_matches(
        self, hash_value: str, size: int, hash_type: HashType | None = None
    ) -> list[Sequence[str]]:
        """Retrieves a list of (folder, filename) tuples based on a given hash.

        Args:
            hash_value: The hash value to search for.
            size: file size

        Returns:
            A list of (folder, filename) tuples, or an empty list if no matches found.
        """

        try:
            cursor = await self.db_conn.cursor()
            if hash_type:
                await cursor.execute(
                    "SELECT files.folder, files.download_filename,files.date FROM hash JOIN files ON hash.folder = files.folder AND hash.download_filename = files.download_filename WHERE hash.hash = ? AND files.file_size = ? AND hash.hash_type = ?;",
                    (hash_value, size, hash_type),
                )
                return cast("list", await cursor.fetchall())
            else:
                await cursor.execute(
                    "SELECT files.folder, files.download_filename FROM hash JOIN files ON hash.folder = files.folder AND hash.download_filename = files.download_filename WHERE hash.hash = ? AND files.file_size = ? AND hash.hash_type = ?;",
                    (hash_value, size, hash_type),
                )
                return cast("list", await cursor.fetchall())

        except Exception as e:
            log(f"Error retrieving folder and filename: {e}", 40)
            return []

    async def insert_or_update_hash_db(
        self, file: Path, original_filename: str | None, referer: URL | None, hash_type: HashType, hash_value: str
    ) -> bool:
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

        hash = await self.insert_or_update_hashes(file, hash_type, hash_value)
        updated = await self.insert_or_update_file(file, original_filename, referer)
        return updated and hash

    async def insert_or_update_hashes(self, file: Path, hash_type: HashType, hash_value: str) -> bool:
        try:
            full_path = file.absolute()
            download_filename = str(full_path.name)
            folder = str(full_path.parent)
            cursor = await self.db_conn.cursor()
            insert_query = """INSERT INTO hash (hash, hash_type, folder, download_filename)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(download_filename, folder, hash_type) DO UPDATE SET hash = ?"""
            await cursor.execute(insert_query, (hash_value, hash_type, folder, download_filename, hash_value))
            await self.db_conn.commit()
        except Exception as e:
            console.print(f"Error inserting/updating record: {e}")
            return False
        return True

    async def insert_or_update_file(self, file: Path, original_filename: str | None, referer: URL | None) -> bool:
        try:
            referer_str = str(referer) if referer else None
            full_path = file.absolute()
            file_stat = await asyncio.to_thread(full_path.stat)
            file_size = int(file_stat.st_size)
            file_date = int(file_stat.st_mtime)
            download_filename = full_path.name
            folder = str(full_path.parent)

            cursor = await self.db_conn.cursor()
            insert_query = """INSERT INTO files (folder, original_filename, download_filename, file_size, referer, date)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(download_filename, folder) DO UPDATE
            SET original_filename = ?, file_size = ?, referer = ?, date = ?
            """

            await cursor.execute(
                insert_query,
                (
                    folder,
                    original_filename,
                    download_filename,
                    file_size,
                    referer_str,
                    file_date,
                    original_filename,
                    file_size,
                    referer_str,
                    file_date,
                ),
            )
            await self.db_conn.commit()
        except Exception as e:
            log(f"Error inserting/updating record: {e}", 40)
            return False
        else:
            return True

    async def get_all_unique_hashes(self, hash_type: HashType | None = None) -> Iterable[Sequence[str]]:
        """Retrieves a list of hashes

        Args:
            hash_value: The hash value to search for.
            hash_type: The type of hash[optional]

        Returns:
            A list of (folder, filename) tuples, or an empty list if no matches found.
        """
        try:
            cursor = await self.db_conn.cursor()

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
            log(f"Error retrieving folder and filename: {e}", 40)
            return []
