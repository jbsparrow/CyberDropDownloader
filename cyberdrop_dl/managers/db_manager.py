from __future__ import annotations

from dataclasses import field
from typing import TYPE_CHECKING

import aiosqlite

from cyberdrop_dl.utils.database.tables.hash_table import HashTable
from cyberdrop_dl.utils.database.tables.history_table import HistoryTable
from cyberdrop_dl.utils.database.tables.temp_referer_table import TempRefererTable
from cyberdrop_dl.utils.database.tables.temp_table import TempTable

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
        self.temp_table: TempTable = field(init=False)
        self.temp_referer_table: TempRefererTable = field(init=False)

    async def startup(self) -> None:
        """Startup process for the DBManager."""
        self._db_conn = await aiosqlite.connect(self._db_path)

        self.ignore_history = self.manager.config_manager.settings_data.runtime_options.ignore_history

        self.history_table = HistoryTable(self._db_conn)
        self.hash_table = HashTable(self._db_conn)
        self.temp_table = TempTable(self._db_conn)
        self.temp_referer_table = TempRefererTable(self._db_conn)

        self.history_table.ignore_history = self.ignore_history
        self.temp_referer_table.ignore_history = self.ignore_history

        await self._pre_allocate()

        await self.history_table.startup()
        await self.hash_table.startup()
        await self.temp_table.startup()
        await self.temp_referer_table.startup()

    async def close(self) -> None:
        """Close the DBManager."""
        await self.temp_referer_table.sql_drop_temp_referers()
        await self._db_conn.close()

    async def _pre_allocate(self) -> None:
        """We pre-allocate 100MB of space to the SQL file just in case the user runs out of disk space."""
        create_pre_allocation_table = "CREATE TABLE IF NOT EXISTS t(x);"
        drop_pre_allocation_table = "DROP TABLE t;"

        fill_pre_allocation = "INSERT INTO t VALUES(zeroblob(100*1024*1024));"  # 100 mb
        check_pre_allocation = "PRAGMA freelist_count;"

        result = await self._db_conn.execute(check_pre_allocation)
        free_space = await result.fetchone()

        if free_space[0] <= 1024:
            await self._db_conn.execute(create_pre_allocation_table)
            await self._db_conn.commit()
            await self._db_conn.execute(fill_pre_allocation)
            await self._db_conn.commit()
            await self._db_conn.execute(drop_pre_allocation_table)
            await self._db_conn.commit()
