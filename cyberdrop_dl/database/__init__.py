from __future__ import annotations

from typing import TYPE_CHECKING

import aiosqlite

from .tables import HashTable, HistoryTable, SchemaVersionTable, TempRefererTable

if TYPE_CHECKING:
    from pathlib import Path


class Database:
    def __init__(self, db_path: Path, ignore_history: bool) -> None:
        self._db_conn: aiosqlite.Connection
        self._db_path: Path = db_path
        self.ignore_history = ignore_history
        self.history_table: HistoryTable
        self.hash_table: HashTable
        self.temp_referer_table: TempRefererTable

    async def startup(self) -> None:
        """Startup process for the DBManager."""
        self._db_conn = await aiosqlite.connect(self._db_path)
        self._db_conn.row_factory = aiosqlite.Row
        self.history_table = HistoryTable(self)
        self.hash_table = HashTable(self)
        self.temp_referer_table = TempRefererTable(self)
        self._schema_versions = SchemaVersionTable(self)

        await self._pre_allocate()
        await self.history_table.startup()
        await self.hash_table.startup()
        await self.temp_referer_table.startup()
        await self._schema_versions.startup()

    async def close(self) -> None:
        """Close the DBManager."""
        await self.temp_referer_table.sql_drop_temp_referers()
        await self._db_conn.close()

    async def _pre_allocate(self) -> None:
        """We pre-allocate 100MB of space to the SQL file just in case the user runs out of disk space."""

        pre_allocate_script = (
            "CREATE TABLE IF NOT EXISTS t(x);"
            "INSERT INTO t VALUES(zeroblob(100*1024*1024));"  # 100 MB
            "DROP TABLE t;"
        )

        free_pages_query = "PRAGMA freelist_count;"
        cursor = await self._db_conn.execute(free_pages_query)
        free_space = await cursor.fetchone()

        if free_space and free_space[0] <= 1024:
            await self._db_conn.executescript(pre_allocate_script)
            await self._db_conn.commit()


__all__ = ["Database"]
