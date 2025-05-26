from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from shutil import copy2
from typing import TYPE_CHECKING

import aiosqlite

from cyberdrop_dl.database.backends.sqlite.tables import SQliteHashTable, SQliteHistoryTable, SQliteTempRefererTable
from cyberdrop_dl.database.backends.sqlite.tables.definitions import create_files, create_temp_hash
from cyberdrop_dl.database.base import Database
from cyberdrop_dl.types import HashAlgorithm
from cyberdrop_dl.utils.logger import log

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Iterable

V6_FILES_TABLE_VALUES = tuple[str, str, str, int | None, str, int]
V6_HASH_TABLE_VALUES = tuple[str, str, str, str]


class SQLiteDatabase(Database):
    def __init__(self, db_path: Path, ignore_history: bool = False) -> None:
        self.ignore_history = ignore_history
        self._db_path = db_path
        self._connection: aiosqlite.Connection | None = None
        self._lock = asyncio.Lock()

    async def _get_connection(self) -> aiosqlite.Connection:
        async with self._lock:
            if self._connection is None:
                self._connection = await aiosqlite.connect(self._db_path)
        return self._connection

    @asynccontextmanager
    async def get_cursor(
        self, commit_on_exit: bool = False, *, startup: bool = False
    ) -> AsyncGenerator[aiosqlite.Cursor]:
        conn = await self._get_connection()
        async with conn.cursor() as cursor:
            try:
                yield cursor
                if commit_on_exit:
                    await conn.commit()
            except Exception as e:
                if commit_on_exit:
                    await conn.rollback()
                if startup:
                    raise
                log(f"Database error: {e!r}", 40)

    @asynccontextmanager
    async def get_transaction_cursor(self) -> AsyncGenerator[aiosqlite.Cursor]:
        async with self.get_cursor(commit_on_exit=True) as cursor:
            yield cursor

    async def close(self) -> None:
        async with self._lock:
            if self._connection is not None:
                await self._connection.execute("DROP TABLE IF EXISTS temp_referer")
                await self._connection.commit()
                await self._connection.close()
                self._connection = None

    async def connect(self) -> None:
        if not await asyncio.to_thread(self._db_path.is_file):
            _ = await self._get_connection()
            return

        async with self.get_cursor(commit_on_exit=True, startup=True) as cursor:
            if await _needs_v5_to_v6_transfer(cursor):
                _make_database_file_backup(self._db_path)
                await _transfer_v5_db_to_v6(cursor)

    async def create_tables(self) -> None:
        async with self.get_transaction_cursor() as cursor:
            await _pre_allocate_100mb(cursor)

        self.hash_table = SQliteHashTable(self)
        self.history_table = SQliteHistoryTable(self)
        self.temp_referer_table = SQliteTempRefererTable(self)
        for table in self.get_tables():
            await table.create()


async def _pre_allocate_100mb(cursor: aiosqlite.Cursor) -> None:
    """We pre-allocate 100MB of space to the SQL file just in case the user runs out of disk space."""
    create_fill_and_drop_fake_table = """
    CREATE TABLE IF NOT EXISTS t(x);
    INSERT INTO t VALUES(zeroblob(100*1024*1024));
    DROP TABLE t;"""

    await cursor.execute("PRAGMA freelist_count;")
    free_space = await cursor.fetchone()
    assert free_space

    if free_space[0] > 1024:
        await cursor.executescript(create_fill_and_drop_fake_table)


async def _transfer_v5_db_to_v6(cursor: aiosqlite.Cursor) -> None:
    """Transfers data from the old 'hash' table to new 'files' and 'temp_hash' tables"""
    await cursor.execute("""SELECT folder, download_filename, file_size, hash, original_filename, referer FROM hash""")
    v5_hash_rows = await cursor.fetchall()
    await _create_new_v6_tables(cursor)
    await _copy_v5_data_to_v6_tables(cursor, v5_hash_rows)


async def _needs_v5_to_v6_transfer(cursor: aiosqlite.Cursor) -> bool:
    await cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='hash'")
    hash_table_exists = await cursor.fetchone() is not None
    if not hash_table_exists:
        log("Old 'hash' table not found. Skipping transfer", 30)
        return False

    await cursor.execute("SELECT COUNT(*) FROM pragma_table_info('hash') WHERE name='hash_type'")
    result = await cursor.fetchone()
    has_hash_type_column = result and result[0] > 0
    if has_hash_type_column:
        return False
    return True


async def _create_new_v6_tables(cursor: aiosqlite.Cursor) -> None:
    drop_old_files_and_temp_hash_tables = """
    DROP TABLE IF EXISTS files;
    DROP TABLE IF EXISTS temp_hash;
    """
    await cursor.executescript(drop_old_files_and_temp_hash_tables)
    await cursor.execute(create_temp_hash)
    await cursor.execute(create_files)


async def _copy_v5_data_to_v6_tables(cursor: aiosqlite.Cursor, v5_hash_rows: Iterable[aiosqlite.Row]) -> None:
    data_to_insert_files, data_to_insert_hash = await _generate_v6_files_and_hash_values(v5_hash_rows)
    query_to_insert_files = """
    INSERT OR IGNORE INTO files (folder, download_filename,
    original_filename, file_size, referer, date) VALUES (?, ?, ?, ?, ?, ?);"""
    query_to_insert_hash = """"
    INSERT OR IGNORE INTO temp_hash (folder, download_filename, hash_type, hash) VALUES (?, ?, ?, ?);"""
    await cursor.executemany(query_to_insert_files, data_to_insert_files)
    await cursor.executemany(query_to_insert_hash, data_to_insert_hash)
    await cursor.execute("DROP TABLE hash")
    await cursor.execute("ALTER TABLE temp_hash RENAME TO hash")


async def _generate_v6_files_and_hash_values(
    v5_hash_rows: Iterable[aiosqlite.Row],
) -> tuple[list[V6_FILES_TABLE_VALUES], list[V6_HASH_TABLE_VALUES]]:
    now = int(datetime.now(UTC).timestamp())
    tasks = [_v5_row_to_v6_values(row, now) for row in v5_hash_rows]
    results = await asyncio.gather(*tasks)
    data_to_insert_files = [pair[0] for pair in results]
    data_to_insert_hash = [pair[1] for pair in results]
    return data_to_insert_files, data_to_insert_hash


async def _v5_row_to_v6_values(
    row: aiosqlite.Row, default_timestamp: int
) -> tuple[V6_FILES_TABLE_VALUES, V6_HASH_TABLE_VALUES]:
    """Generates v6 data from a row of a v5 `hash` table.

    Returns 2 tuples:
        First tuple: values to create a new row in a v6 `files` table,
        Second tuple: values to create a new row in a v6 `hash` table"""
    folder, download_filename, file_size, hash, original_filename, referer = row
    file_path = Path(folder, download_filename)
    try:
        stat = await asyncio.to_thread(file_path.stat)
        file_date = int(stat.st_mtime)
    except OSError:
        file_date = default_timestamp

    insert_files: V6_FILES_TABLE_VALUES = (folder, download_filename, original_filename, file_size, referer, file_date)
    insert_hash: V6_HASH_TABLE_VALUES = (folder, download_filename, HashAlgorithm.md5, hash)
    return insert_files, insert_hash


def _make_database_file_backup(db_path: Path) -> None:
    new_file = db_path.with_name(f"cyberdrop_v5_{datetime.now().strftime('%Y%m%d_%H%M%S')}.bak.db")
    copy2(db_path, new_file)
