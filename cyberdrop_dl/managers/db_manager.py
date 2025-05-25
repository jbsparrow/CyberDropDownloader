from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from shutil import copy2
from typing import TYPE_CHECKING, Any

import aiosqlite
from rich import print as rprint

from cyberdrop_dl.types import HashAlgorithm
from cyberdrop_dl.utils.database.table_definitions import create_files, create_temp_hash
from cyberdrop_dl.utils.database.tables import hash_table, history_table, temp_referer_table

if TYPE_CHECKING:
    from collections.abc import Iterable

    _db_conn: aiosqlite.Connection
    _ignore_history: bool
    _db_path: Path
else:
    _db_conn = None


async def startup(db_path: Path, ignore_history: bool = False) -> None:
    """Startup process for the DBManager."""
    global _db_conn, _ignore_history, _db_path
    db_file_exists = db_path.is_file()
    if _db_conn is not None:
        await _db_conn.close()

    _db_conn = await aiosqlite.connect(db_path)
    _db_path = db_path
    _ignore_history = ignore_history
    if db_file_exists:
        await try_transfer_v5_db_to_v6()

    await _init()


async def _init() -> None:
    await _pre_allocate_100mb()
    await hash_table.startup(_db_conn)
    await history_table.startup(_db_conn, _ignore_history)
    await temp_referer_table.startup(_db_conn, _ignore_history)
    await history_table.delete_invalid_rows()


async def close() -> None:
    await temp_referer_table.sql_drop_temp_referers()
    await _db_conn.close()


async def _pre_allocate_100mb() -> None:
    """We pre-allocate 100MB of space to the SQL file just in case the user runs out of disk space."""
    create_fill_and_drop_table = (
        "CREATE TABLE IF NOT EXISTS t(x);",
        "INSERT INTO t VALUES(zeroblob(100*1024*1024));",
        "DROP TABLE t;",
    )

    result = await _db_conn.execute("PRAGMA freelist_count;")
    free_space = await result.fetchone()
    assert free_space

    if free_space[0] > 1024:
        for query in create_fill_and_drop_table:
            await _db_conn.execute(query)
            await _db_conn.commit()


async def try_transfer_v5_db_to_v6() -> None:
    """Transfers data from the old 'hash' table to new 'files' and 'temp_hash' tables"""
    cursor = await _db_conn.cursor()
    try:
        # Check if the 'hash' table exists
        if not _needs_transfer(cursor):
            return
        _make_db_file_backup()
        old_hash_data = await _get_old_v5_hash_data(cursor)
        await _create_new_v6_tables(cursor)
        await _copy_v5_data_to_v6_tables(cursor, old_hash_data)
        await _db_conn.commit()
    except Exception:
        await _db_conn.rollback()
        raise


async def _needs_transfer(cursor: aiosqlite.Cursor) -> bool:
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


async def _get_file_info(row: aiosqlite.Row, now: int) -> tuple[tuple, tuple]:
    folder, download_filename, file_size, hash, original_filename, referer = row
    file_path = Path(folder, download_filename)
    try:
        stat = await asyncio.to_thread(file_path.stat)
        file_date = int(stat.st_mtime)
    except OSError:
        file_date = now

    insert_files = (folder, download_filename, original_filename, file_size, referer, file_date)
    insert_hash = (folder, download_filename, HashAlgorithm.md5, hash)
    return insert_files, insert_hash


def _make_db_file_backup() -> None:
    new_file = Path(_db_path.parent, f"cyberdrop_v5_{datetime.now().strftime('%Y%m%d_%H%M%S')}.bak.db")
    copy2(_db_path, new_file)
