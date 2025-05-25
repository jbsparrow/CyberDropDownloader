from __future__ import annotations

from dataclasses import field
from typing import TYPE_CHECKING

import aiosqlite

from cyberdrop_dl.utils.database.tables import hash_table, history_table
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
        self.temp_referer_table: TempRefererTable = field(init=False)

    async def startup(self) -> None:
        """Startup process for the DBManager."""
        self._db_conn = await aiosqlite.connect(self._db_path)
        self.ignore_history = self.manager.config_manager.settings_data.runtime_options.ignore_history
        history_table.init(self._db_conn, self.ignore_history)
        hash_table.init(self._db_conn)
        self.temp_referer_table = TempRefererTable(self._db_conn)
        self.temp_referer_table.ignore_history = self.ignore_history
        await self._pre_allocate()
        await history_table.startup()
        await hash_table.startup()
        await self.temp_referer_table.startup()
        await self.run_fixes()

    async def run_fixes(self):
        if not self.manager.cache_manager.get("fixed_empty_download_filenames"):
            await history_table.delete_invalid_rows()
            self.manager.cache_manager.save("fixed_empty_download_filenames", True)

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
        assert free_space

        if free_space[0] <= 1024:
            await self._db_conn.execute(create_pre_allocation_table)
            await self._db_conn.commit()
            await self._db_conn.execute(fill_pre_allocation)
            await self._db_conn.commit()
            await self._db_conn.execute(drop_pre_allocation_table)
            await self._db_conn.commit()
