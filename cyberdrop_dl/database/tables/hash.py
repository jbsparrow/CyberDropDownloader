from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, cast

from cyberdrop_dl.utils.logger import log

from .definitions import create_files, create_hash

if TYPE_CHECKING:
    import aiosqlite
    from yarl import URL

    from cyberdrop_dl.database import Database


class HashTable:
    def __init__(self, database: Database) -> None:
        self._database = database

    @property
    def db_conn(self) -> aiosqlite.Connection:
        return self._database._db_conn

    async def startup(self) -> None:
        """Startup process for the HistoryTable."""
        await self.db_conn.execute(create_files)
        await self.db_conn.execute(create_hash)
        await self.db_conn.commit()

    async def get_file_hash_exists(self, path: Path | str, hash_type: str) -> str | None:
        """gets the hash from a complete file path

        Args:
            full_path: Full path to the file to check.

        Returns:
            hash if  exists
        """
        query = "SELECT hash FROM hash WHERE folder=? AND download_filename=? AND hash_type=? AND hash IS NOT NULL"
        try:
            path = Path(path)
            if not path.is_absolute():
                path = path.absolute()
            folder = str(path.parent)
            filename = path.name

            # Check if the file exists with matching folder, filename, and size
            cursor = await self.db_conn.execute(query, (folder, filename, hash_type))
            if row := await cursor.fetchone():
                return row[0]

        except Exception as e:
            log(f"Error checking file: {e}", 40, exc_info=e)

    async def get_files_with_hash_matches(
        self, hash_value: str, size: int, hash_type: str | None = None
    ) -> list[aiosqlite.Row]:
        """Retrieves a list of (folder, filename) tuples based on a given hash.

        Args:
            hash_value: The hash value to search for.
            size: file size

        Returns:
            A list of (folder, filename) tuples, or an empty list if no matches found.
        """
        if hash_type:
            query = """
            SELECT files.folder, files.download_filename,files.date
            FROM hash JOIN files ON hash.folder = files.folder AND hash.download_filename = files.download_filename
            WHERE hash.hash = ? AND files.file_size = ? AND hash.hash_type = ?;
            """

        else:
            query = """
            SELECT files.folder, files.download_filename FROM hash JOIN files
            ON hash.folder = files.folder AND hash.download_filename = files.download_filename
            WHERE hash.hash = ? AND files.file_size = ? AND hash.hash_type = ?;
            """

        try:
            cursor = await self.db_conn.execute(query, (hash_value, size, hash_type))
            return cast("list[aiosqlite.Row]", await cursor.fetchall())

        except Exception as e:
            log(f"Error retrieving folder and filename: {e}", 40, exc_info=e)
            return []

    async def check_hash_exists(self, hash_type: str, hash_value: str) -> bool:
        if self._database.ignore_history:
            return False

        query = "SELECT 1 FROM hash WHERE hash.hash_type = ? AND hash.hash = ? LIMIT 1"
        cursor = await self.db_conn.execute(query, (hash_type, hash_value))
        result = await cursor.fetchone()
        return result is not None

    async def insert_or_update_hash_db(
        self, hash_value: str, hash_type: str, file: Path | str, original_filename: str | None, referer: URL | None
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

        hash = await self.insert_or_update_hashes(hash_value, hash_type, file)
        file_ = await self.insert_or_update_file(original_filename, referer, file)
        return file_ and hash

    async def insert_or_update_hashes(self, hash_value: str, hash_type: str, file: Path | str) -> bool:
        query = """
        INSERT INTO hash (hash, hash_type, folder, download_filename)
        VALUES (?, ?, ?, ?) ON CONFLICT(download_filename, folder, hash_type) DO UPDATE SET hash = ?;
        """

        try:
            full_path = Path(file)
            if not full_path.is_absolute():
                full_path = full_path.absolute()
            download_filename = full_path.name
            folder = str(full_path.parent)
            await self.db_conn.execute(query, (hash_value, hash_type, folder, download_filename, hash_value))
            await self.db_conn.commit()
        except Exception as e:
            log(f"Error inserting/updating record: {e}", 40, exc_info=e)
            return False
        return True

    async def insert_or_update_file(
        self, original_filename: str | None, referer: URL | str | None, file: Path | str
    ) -> bool:
        query = """
        INSERT INTO files (folder, original_filename, download_filename, file_size, referer, date)
        VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(download_filename, folder)
        DO UPDATE SET original_filename = ?, file_size = ?, referer = ?, date = ?;
        """
        referer_ = str(referer) if referer else None
        try:
            full_path = Path(file)
            if not full_path.is_absolute():
                full_path = full_path.absolute()
            download_filename = full_path.name
            folder = str(full_path.parent)
            stat = full_path.stat()
            file_size = stat.st_size
            file_date = int(stat.st_mtime)
            await self.db_conn.execute(
                query,
                (
                    folder,
                    original_filename,
                    download_filename,
                    file_size,
                    referer_,
                    file_date,
                    original_filename,
                    file_size,
                    referer_,
                    file_date,
                ),
            )
            await self.db_conn.commit()
        except Exception as e:
            log(f"Error inserting/updating record: {e}", 40, exc_info=e)
            return False
        return True

    async def get_all_unique_hashes(self, hash_type: str | None = None) -> list[str]:
        """Retrieves a list of hashes

        Args:
            hash_value: The hash value to search for.
            hash_type: The type of hash[optional]

        Returns:
            A list of (folder, filename) tuples, or an empty list if no matches found.
        """
        if hash_type:
            query, params = "SELECT DISTINCT hash FROM hash WHERE hash_type =?", (hash_type,)

        else:
            query, params = "SELECT DISTINCT hash FROM hash", ()
        try:
            cursor = await self.db_conn.execute(query, params)
            rows = await cursor.fetchall()
            return [row[0] for row in rows]
        except Exception as e:
            log(f"Error retrieving folder and filename: {e}", 40, exc_info=e)
            return []
