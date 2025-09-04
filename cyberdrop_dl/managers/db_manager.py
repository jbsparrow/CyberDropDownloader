from __future__ import annotations

from dataclasses import field
from typing import TYPE_CHECKING

import aiosqlite

from cyberdrop_dl.utils.database.tables.hash_table import HashTable
from cyberdrop_dl.utils.database.tables.history_table import HistoryTable
from cyberdrop_dl.utils.database.tables.temp_referer_table import TempRefererTable

if TYPE_CHECKING:
    from pathlib import Path

    from cyberdrop_dl.managers.manager import Manager


class DBManager:
    def __init__(self, manager: Manager, db_path: Path) -> None:
        self.manager = manager
        self._db_conn: aiosqlite.Connection = field(init=False)
        self._db_path: Path = db_path

        self.ignore_history: bool = False

        self.history_table: HistoryTable = field(init=False)
        self.hash_table: HashTable = field(init=False)
        self.temp_referer_table: TempRefererTable = field(init=False)

    async def startup(self) -> None:
        """Startup process for the DBManager."""
        self._db_conn = await aiosqlite.connect(self._db_path)
        self._db_conn._conn.row_factory = aiosqlite.Row

        self.ignore_history = self.manager.config_manager.settings_data.runtime_options.ignore_history

        self.history_table = HistoryTable(self)
        self.hash_table = HashTable(self)
        self.temp_referer_table = TempRefererTable(self)

        await self._pre_allocate()
        await self.history_table.startup()
        await self.hash_table.startup()
        await self.temp_referer_table.startup()
        await self.run_fixes()

    async def run_fixes(self):
        if not self.manager.cache_manager.get("fixed_empty_download_filenames"):
            await self.history_table.delete_invalid_rows()
            self.manager.cache_manager.save("fixed_empty_download_filenames", True)

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
