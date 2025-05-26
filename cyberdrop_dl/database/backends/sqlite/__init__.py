import asyncio
from collections.abc import AsyncGenerator, Iterable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from shutil import copy2
from typing import Any

import aiosqlite
from rich import print as rprint

from cyberdrop_dl.database.backends.sqlite.tables import SQliteHashTable, SQliteHistoryTable
from cyberdrop_dl.database.backends.sqlite.tables.definitions import create_files, create_temp_hash
from cyberdrop_dl.database.base import DBBackend
from cyberdrop_dl.types import HashAlgorithm
from cyberdrop_dl.utils.database.tables import temp_referer_table
from cyberdrop_dl.utils.logger import log


class SQLiteDatabase(DBBackend):
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
    async def get_connection(self, commit_on_exit: bool = False) -> AsyncGenerator[aiosqlite.Connection]:
        conn = await self._get_connection()
        try:
            yield conn
            if commit_on_exit:
                await conn.commit()
        except Exception as e:
            if commit_on_exit:
                await conn.rollback()
            log(f"Database error: {e!r}", 40)
            raise

    @asynccontextmanager
    async def get_cursor(self, commit_on_exit: bool = False) -> AsyncGenerator[aiosqlite.Cursor]:
        async with self.get_connection(commit_on_exit=commit_on_exit) as conn, conn.cursor() as cursor:
            yield cursor

    @asynccontextmanager
    async def get_transaction_cursor(self) -> AsyncGenerator[aiosqlite.Cursor]:
        async with self.get_cursor(commit_on_exit=True) as cursor:
            yield cursor

    async def close(self) -> None:
        async with self._lock:
            if self._connection is not None:
                await temp_referer_table.sql_drop_temp_referers()
                await self._connection.close()
                self._connection = None

    async def connect(self) -> None:
        if not self._db_path.is_file():
            _ = await self._get_connection()
            return

        async with self.get_transaction_cursor() as cursor:
            if await _needs_v5_to_v6_transfer(cursor):
                _make_database_file_backup(self._db_path)
                await _try_transfer_v5_db_to_v6(cursor)

    async def create_tables(self) -> None:
        async with self.get_transaction_cursor() as cursor:
            await _pre_allocate_100mb(cursor)

        self.hash_table = SQliteHashTable(self)
        self.history_table = SQliteHistoryTable(self)
        for table in self.get_tables():
            await table.create()


async def _pre_allocate_100mb(cursor: aiosqlite.Cursor) -> None:
    """We pre-allocate 100MB of space to the SQL file just in case the user runs out of disk space."""
    create_fill_and_drop_table = """
    CREATE TABLE IF NOT EXISTS t(x);
    INSERT INTO t VALUES(zeroblob(100*1024*1024));
    DROP TABLE t;"""

    result = await cursor.execute("PRAGMA freelist_count;")
    free_space = await result.fetchone()
    assert free_space

    if free_space[0] > 1024:
        await cursor.executescript(create_fill_and_drop_table)


async def _try_transfer_v5_db_to_v6(cursor: aiosqlite.Cursor) -> None:
    """Transfers data from the old 'hash' table to new 'files' and 'temp_hash' tables"""
    old_hash_data = await _get_old_v5_hash_data(cursor)
    await _create_new_v6_tables(cursor)
    await _copy_v5_data_to_v6_tables(cursor, old_hash_data)


async def _needs_v5_to_v6_transfer(cursor: aiosqlite.Cursor) -> bool:
    await cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='hash'")
    hash_table_exists = await cursor.fetchone() is not None

    if not hash_table_exists:
        rprint("[bold yellow]Old 'hash' table not found. Skipping transfer.[/]")
        return False

    # Check if the 'hash_type' column exists in the 'hash' table
    await cursor.execute("SELECT COUNT(*) FROM pragma_table_info('hash') WHERE name='hash_type'")
    result = await cursor.fetchone()
    has_hash_type_column = result and result[0] > 0
    if has_hash_type_column:
        return False
    return True


async def _get_old_v5_hash_data(cursor: aiosqlite.Cursor) -> Iterable[aiosqlite.Row]:
    # Fetch data from the old 'hash' table
    query = """SELECT folder, download_filename, file_size, hash, original_filename, referer FROM hash"""
    await cursor.execute(query)
    return await cursor.fetchall()


async def _create_new_v6_tables(cursor: aiosqlite.Cursor) -> None:
    # Drop existing 'files' and 'temp_hash' tables if they exist
    await cursor.execute("DROP TABLE IF EXISTS files")
    await cursor.execute("DROP TABLE IF EXISTS temp_hash")
    # Create the 'temp_hash' table with the required schema
    await cursor.execute(create_temp_hash)
    await cursor.execute(create_files)


async def _copy_v5_data_to_v6_tables(cursor: aiosqlite.Cursor, old_hash_data: Iterable[aiosqlite.Row]) -> None:
    # Prepare data for insertion into 'files' and 'temp_hash' tables
    data_to_insert_files, data_to_insert_hash = await _generate_hash_and_files_tables_data(old_hash_data)

    # Insert data into 'files' and 'temp_hash' tables
    query = "INSERT OR IGNORE INTO files (folder, download_filename, original_filename, file_size, referer, date) VALUES (?, ?, ?, ?, ?, ?);"
    await cursor.executemany(query, data_to_insert_files)

    query = "INSERT OR IGNORE INTO temp_hash (folder, download_filename, hash_type, hash) VALUES (?, ?, ?, ?);"
    await cursor.executemany(query, data_to_insert_hash)
    await cursor.execute("DROP TABLE hash")
    await cursor.execute("ALTER TABLE temp_hash RENAME TO hash")


async def _generate_hash_and_files_tables_data(old_hash_data: Iterable[aiosqlite.Row]) -> tuple[list[Any], list[Any]]:
    now = int(datetime.now(UTC).timestamp())
    tasks = [_get_file_info(row, now) for row in old_hash_data]
    results = await asyncio.gather(*tasks)
    data_to_insert_files = [pair[0] for pair in results]
    data_to_insert_hash = [pair[1] for pair in results]
    return data_to_insert_files, data_to_insert_hash


async def _get_file_info(row: aiosqlite.Row, default_timestamp: int) -> tuple[tuple, tuple]:
    folder, download_filename, file_size, hash, original_filename, referer = row
    file_path = Path(folder, download_filename)
    try:
        stat = await asyncio.to_thread(file_path.stat)
        file_date = int(stat.st_mtime)
    except OSError:
        file_date = default_timestamp

    insert_files = (folder, download_filename, original_filename, file_size, referer, file_date)
    insert_hash = (folder, download_filename, HashAlgorithm.md5, hash)
    return insert_files, insert_hash


def _make_database_file_backup(_db_path: Path) -> None:
    new_file = Path(_db_path.parent, f"cyberdrop_v5_{datetime.now().strftime('%Y%m%d_%H%M%S')}.bak.db")
    copy2(_db_path, new_file)
