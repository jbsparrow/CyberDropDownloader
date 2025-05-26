from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING

from cyberdrop_dl.database.backends.sqlite.tables.definitions import create_files, create_hash
from cyberdrop_dl.database.base import HashTable

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    import aiosqlite

    from cyberdrop_dl.database.backends.sqlite import SQLiteDatabase
    from cyberdrop_dl.types import AbsoluteHttpURL, Hash, HashAlgorithm


class SQliteHashTable(HashTable):
    def __init__(self, database: SQLiteDatabase) -> None:
        self.db = database

    async def create(self) -> None:
        async with self.db.get_transaction_cursor() as cursor:
            await cursor.execute(create_files)
            await cursor.execute(create_hash)

    async def get_file_hash_if_exists(self, file: Path, hash_type: HashAlgorithm) -> Hash | None:
        query = "SELECT hash FROM hash WHERE folder=? AND download_filename=? AND hash_type=? AND hash IS NOT NULL"
        folder = str(file.parent)

        async with self.db.get_cursor() as cursor:
            await cursor.execute(query, (folder, file.name, hash_type))
            result = await cursor.fetchone()
            if result:
                return hash_type.create_hash(result[0])

    async def get_files_with_hash_matches(self, hash: Hash, size: int) -> AsyncGenerator[Path]:
        """Yields paths of every file that matches the given hash and size."""

        query = """
        SELECT files.folder, files.download_filename, files.date
        FROM hash JOIN files ON hash.folder = files.folder AND hash.download_filename = files.download_filename
        WHERE hash.hash = ? AND files.file_size = ? AND hash.hash_type = ?;"""

        async with self.db.get_cursor() as cursor:
            await cursor.execute(query, (hash.value, size, hash.algorithm))
            for row in await cursor.fetchall():
                yield Path(*row[:2])

    async def insert_or_update_hash_db(
        self, file: Path, original_filename: str | None, referer: AbsoluteHttpURL | None, hash: Hash
    ) -> bool:
        """Inserts or updates a record in the specified SQLite database.

        :param file: The file path.
        :param original_filename: The original name of the file (optional).
        :param referer: The referer URL (optional).
        :param hash: The hash object.
        :return: `True` if the record was inserted or updated successfully, `False` otherwise.
        """

        try:
            async with self.db.get_transaction_cursor() as cursor:
                await _insert_or_update_hashes(cursor, file, hash)
                await _insert_or_update_file(cursor, file, original_filename, referer)
        except Exception:
            return False
        else:
            return True


async def _insert_or_update_hashes(cursor: aiosqlite.Cursor, file: Path, hash: Hash) -> None:
    """Inserts or updates the hash information for a specific file.

    :param file: The path to the file.
    :param hash: The hash object (e.g., md5, sha256).
    :return: `True` if the hash information was successfully inserted or updated, `False` otherwise.
    """
    query = """
    INSERT INTO hash (hash, hash_type, folder, download_filename)
    VALUES (?, ?, ?, ?)
    ON CONFLICT(download_filename, folder, hash_type) DO UPDATE SET hash = ?"""
    folder = str(file.parent)
    insert_values = hash, hash.algorithm, folder, file.name
    on_conflict_update = (hash.value,)
    await cursor.execute(query, (*insert_values, *on_conflict_update))


async def _insert_or_update_file(
    cursor: aiosqlite.Cursor, file: Path, original_filename: str | None, referer: AbsoluteHttpURL | None
) -> None:
    """Inserts or updates a file record in the database.

    :param file: The path to the file.
    :param original_filename: The original name of the file (optional).
    :param referer: The referer URL associated with the file (optional).
    :return: `True` if the file record was successfully inserted or updated, `False` otherwise.
    """
    query = """
    INSERT INTO files (folder, original_filename, download_filename, file_size, referer, date)
    VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(download_filename, folder) DO UPDATE
    SET original_filename = ?, file_size = ?, referer = ?, date = ?
    """
    referer_str = str(referer) if referer else None
    file_stat = await asyncio.to_thread(file.stat)
    file_size = int(file_stat.st_size)
    file_date = int(file_stat.st_mtime)
    folder = str(file.parent)

    insert_values = folder, original_filename, file.name, file_size, referer_str, file_date
    on_conflict_update = original_filename, file_size, referer_str, file_date
    await cursor.execute(query, (*insert_values, *on_conflict_update))
