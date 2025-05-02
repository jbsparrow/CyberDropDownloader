from __future__ import annotations

import asyncio
import contextlib
from typing import TYPE_CHECKING, TypeAlias, cast

from cyberdrop_dl.utils.constants import HashValue
from cyberdrop_dl.utils.database.table_definitions import create_files, create_hash
from cyberdrop_dl.utils.logger import log

if TYPE_CHECKING:
    from pathlib import Path

    import aiosqlite
    from yarl import URL

    from cyberdrop_dl.utils.constants import HashType


FileEntry: TypeAlias = tuple[str, str, int]  # folder, filename and date


@contextlib.contextmanager
def log_execute_error(msg: str):
    try:
        yield
    except Exception as e:
        log(f"{msg}: {e!r}", 40)


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

    async def get_file_hash_exists(self, path: Path, hash_type: HashType) -> HashValue | None:
        """Gets the hash from a file if it exists in the database.

        :param path: Path to the file to check.
        :param hash_type: The type of hash to retrieve.
        :return: The hash value if a hash for that file exists in the database, otherwise `None`.
        """
        with log_execute_error("Error checking file"):
            folder = str(path.parent)
            filename = path.name
            cursor = await self.db_conn.cursor()
            query = "SELECT hash FROM hash WHERE folder=? AND download_filename=? AND hash_type=? AND hash IS NOT NULL"
            await cursor.execute(query, (folder, filename, hash_type))
            result = await cursor.fetchone()
            if result:
                return HashValue(result[0])

    async def get_files_with_hash_matches(
        self, hash_value: HashValue, hash_type: HashType, size: int
    ) -> list[FileEntry]:
        """Retrieves a list of (folder, filename, date) tuples based on a given hash.

        :param hash_value: The hash value to search for.
        :param size: file size
        :param hash_type: The type of hash being used (e.g., MD5, SHA1).
        :return: A list of (folder, filename, date) tuples, or an empty list if no matches found.
        """

        query = """
        SELECT files.folder, files.download_filename, files.date
        FROM hash JOIN files ON hash.folder = files.folder AND hash.download_filename = files.download_filename
        WHERE hash.hash = ? AND files.file_size = ? AND hash.hash_type = ?;"""

        with log_execute_error("Error retrieving folder, filename and date"):
            cursor = await self.db_conn.cursor()
            await cursor.execute(query, (hash_value, size, hash_type))
            return cast("list[FileEntry]", await cursor.fetchall())

        return []

    async def insert_or_update_hash_db(
        self, file: Path, original_filename: str | None, referer: URL | None, hash_type: HashType, hash_value: HashValue
    ) -> bool:
        """Inserts or updates a record in the specified SQLite database.

        :param file: The file path.
        :param original_filename: The original name of the file (optional).
        :param referer: The referer URL (optional).
        :param hash_type: The hash type (e.g., md5, sha256).
        :param hash_value: The calculated hash of the file.
        :return: `True` if the record was inserted or updated successfully, `False` otherwise.
        """

        hash_success = await self.insert_or_update_hashes(file, hash_type, hash_value)
        file_success = await self.insert_or_update_file(file, original_filename, referer)
        return file_success and hash_success

    async def insert_or_update_hashes(self, file: Path, hash_type: HashType, hash_value: HashValue) -> bool:
        """Inserts or updates the hash information for a specific file.

        :param file: The path to the file.
        :param hash_type: The type of hash (e.g., md5, sha256).
        :param hash_value: The calculated hash value for the file.
        :return: `True` if the hash information was successfully inserted or updated, `False` otherwise.
        """
        query = """
        INSERT INTO hash (hash, hash_type, folder, download_filename)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(download_filename, folder, hash_type) DO UPDATE SET hash = ?"""

        with log_execute_error("Error inserting/updating record"):
            download_filename = str(file.name)
            folder = str(file.parent)
            cursor = await self.db_conn.cursor()
            await cursor.execute(query, (hash_value, hash_type, folder, download_filename, hash_value))
            await self.db_conn.commit()
            return True
        return False

    async def insert_or_update_file(self, file: Path, original_filename: str | None, referer: URL | None) -> bool:
        """Inserts or updates a file record in the database.

        :param file: The path to the file.
        :param original_filename: The original name of the file (optional).
        :param referer: The referer URL associated with the file (optional).
        :return: `Tru`e if the file record was successfully inserted or updated, `False` otherwise.
        """
        query = """
        INSERT INTO files (folder, original_filename, download_filename, file_size, referer, date)
        VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(download_filename, folder) DO UPDATE
        SET original_filename = ?, file_size = ?, referer = ?, date = ?
        """

        with log_execute_error("Error inserting/updating record"):
            referer_str = str(referer) if referer else None
            file_stat = await asyncio.to_thread(file.stat)
            file_size = int(file_stat.st_size)
            file_date = int(file_stat.st_mtime)
            download_filename = file.name
            folder = str(file.parent)
            cursor = await self.db_conn.cursor()
            await cursor.execute(
                query,
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
            return True

        return False

    async def get_all_unique_hashes(self, hash_type: HashType) -> set[str]:
        """Retrieves a list of unique hashes from the database.

        :param hash_type: The type of hash to filter by (optional).
        :return: A set with each unique hash and its associated data.
        """
        query = "SELECT DISTINCT hash FROM hash WHERE hash_type =?"
        with log_execute_error(f"Error retrieving all {hash_type} hashes"):
            cursor = await self.db_conn.cursor()
            await cursor.execute(query, (hash_type,))
            results = await cursor.fetchall()
            return {x[0] for x in results}
        return set()
