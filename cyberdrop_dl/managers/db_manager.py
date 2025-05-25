from __future__ import annotations

from typing import TYPE_CHECKING

import aiosqlite

from cyberdrop_dl.utils.database.tables import hash_table, history_table, temp_referer_table

if TYPE_CHECKING:
    from pathlib import Path


_db_conn: aiosqlite.Connection
_ignore_history: bool


async def startup(db_path: Path, ignore_history: bool = False) -> None:
    """Startup process for the DBManager."""
    global _db_conn, _ignore_history
    _db_conn = await aiosqlite.connect(db_path)
    _ignore_history: bool = ignore_history
    await _pre_allocate()
    await hash_table.startup(_db_conn)
    await history_table.startup(_db_conn, _ignore_history)
    await temp_referer_table.startup(_db_conn, _ignore_history)
    await history_table.delete_invalid_rows()


async def close() -> None:
    await temp_referer_table.sql_drop_temp_referers()
    await _db_conn.close()


async def _pre_allocate() -> None:
    """We pre-allocate 100MB of space to the SQL file just in case the user runs out of disk space."""
    create_pre_allocation_table = "CREATE TABLE IF NOT EXISTS t(x);"
    drop_pre_allocation_table = "DROP TABLE t;"
    fill_pre_allocation = "INSERT INTO t VALUES(zeroblob(100*1024*1024));"  # 100 mb
    check_pre_allocation = "PRAGMA freelist_count;"

    result = await _db_conn.execute(check_pre_allocation)
    free_space = await result.fetchone()
    assert free_space

    if free_space[0] <= 1024:
        for query in (create_pre_allocation_table, fill_pre_allocation, drop_pre_allocation_table):
            await _db_conn.execute(query)
            await _db_conn.commit()
