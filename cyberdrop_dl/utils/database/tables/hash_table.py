from __future__ import annotations

import asyncio
import contextlib
from pathlib import Path
from typing import TYPE_CHECKING

from cyberdrop_dl.types import AbsoluteHttpURL, Hash
from cyberdrop_dl.utils.database.table_definitions import create_files, create_hash
from cyberdrop_dl.utils.logger import log

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    import aiosqlite

    from cyberdrop_dl.types import HashAlgorithm


@contextlib.contextmanager
def log_if_error(message: str):
    try:
        yield
    except Exception as e:
        log(f"{message}: {e!r}", 40)


_db_conn: aiosqlite.Connection


async def startup(db_conn: aiosqlite.Connection) -> None:
    global _db_conn
    _db_conn: aiosqlite.Connection = db_conn
    await _create_hash_and_files_tables()


async def get_file_hash_if_exists(file: Path, hash_type: HashAlgorithm) -> Hash | None:
    query = "SELECT hash FROM hash WHERE folder=? AND download_filename=? AND hash_type=? AND hash IS NOT NULL"
    folder = str(file.parent)

    with log_if_error("Error checking file"):
        cursor = await _db_conn.cursor()
        await cursor.execute(query, (folder, file.name, hash_type))
        result = await cursor.fetchone()
        if result:
            return Hash(hash_type, result[0])


async def get_files_with_hash_matches(hash: Hash, size: int) -> AsyncGenerator[Path]:
    """Yields paths of every file that matches the given hash and size."""

    query = """
    SELECT files.folder, files.download_filename, files.date
    FROM hash JOIN files ON hash.folder = files.folder AND hash.download_filename = files.download_filename
    WHERE hash.hash = ? AND files.file_size = ? AND hash.hash_type = ?;"""

    with log_if_error("Error retrieving folder, filename and date"):
        cursor = await _db_conn.cursor()
        await cursor.execute(query, (hash.value, size, hash.algorithm))
        for row in await cursor.fetchall():
            yield Path(*row[:2])


async def insert_or_update_hash_db(
    file: Path, original_filename: str | None, referer: AbsoluteHttpURL | None, hash: Hash
) -> bool:
    """Inserts or updates a record in the specified SQLite database.

    :param file: The file path.
    :param original_filename: The original name of the file (optional).
    :param referer: The referer URL (optional).
    :param hash: The hash object.
    :return: `True` if the record was inserted or updated successfully, `False` otherwise.
    """

    hash_insert_was_successful = await _insert_or_update_hashes(file, hash)
    file_insert_was_successful = await _insert_or_update_file(file, original_filename, referer)
    return file_insert_was_successful and hash_insert_was_successful


async def _create_hash_and_files_tables() -> None:
    await _db_conn.execute(create_files)
    await _db_conn.execute(create_hash)
    await _db_conn.commit()


async def _insert_or_update_hashes(file: Path, hash: Hash) -> bool:
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
    with log_if_error("Error inserting/updating record"):
        cursor = await _db_conn.cursor()
        await cursor.execute(query, (*insert_values, *on_conflict_update))
        await _db_conn.commit()
        return True
    return False


async def _insert_or_update_file(file: Path, original_filename: str | None, referer: AbsoluteHttpURL | None) -> bool:
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
    with log_if_error("Error inserting/updating record"):
        cursor = await _db_conn.cursor()
        await cursor.execute(query, (*insert_values, *on_conflict_update))
        await _db_conn.commit()
        return True

    return False
