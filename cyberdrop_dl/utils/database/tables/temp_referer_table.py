from __future__ import annotations

from typing import TYPE_CHECKING

from cyberdrop_dl.utils.database.table_definitions import create_temp_referer

if TYPE_CHECKING:
    import aiosqlite
    from yarl import URL

    from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL


class TempRefererTable:
    def __init__(self, db_conn: aiosqlite.Connection) -> None:
        self.db_conn: aiosqlite.Connection = db_conn
        self.ignore_history: bool = False

    async def startup(self) -> None:
        """Startup process for the TempRefererTable."""
        await self.db_conn.execute(create_temp_referer)
        await self.db_conn.commit()

    async def get_temp_referers(self) -> list[str]:
        """Gets the list of temp referers."""
        cursor = await self.db_conn.cursor()
        await cursor.execute("SELECT referer FROM temp_referer;")
        referers = await cursor.fetchall()
        referers = [list(referer) for referer in referers]
        return list(sum(referers, ()))

    async def sql_insert_temp_referer(self, referer: str) -> None:
        """Inserts a temp referer into the temp_referers table."""
        await self.db_conn.execute("""INSERT OR IGNORE INTO temp_referer VALUES (?)""", (referer,))
        await self.db_conn.commit()

    async def sql_purge_temp_referers(self) -> None:
        """Delete all records in temp_referers table."""
        await self.db_conn.execute("""DELETE FROM temp_referer;""")
        await self.db_conn.commit()

    async def sql_drop_temp_referers(self) -> None:
        """Delete temp_referers table."""
        await self.db_conn.execute("""DROP TABLE IF EXISTS temp_referer""")
        await self.db_conn.commit()

    async def check_referer(self, referer: AbsoluteHttpURL) -> bool:
        """Checks whether an individual referer url has already been recorded in the database."""
        if self.ignore_history:
            return False

        referer_str = str(referer)

        cursor = await self.db_conn.cursor()
        result = await cursor.execute("""SELECT url_path FROM media WHERE referer = ? """, (referer_str,))
        sql_referer_check = await result.fetchone()
        sql_referer_check_current_run = await self._check_temp_referer(referer)
        if not sql_referer_check:
            await self.sql_insert_temp_referer(referer_str)
            return False
        return not sql_referer_check_current_run

    async def _check_temp_referer(self, referer: URL) -> bool:
        """Checks whether an individual referer url has already been recorded in this session."""
        if self.ignore_history:
            return False

        cursor = await self.db_conn.cursor()
        result = await cursor.execute("""SELECT referer FROM temp_referer WHERE referer = ? """, (str(referer),))
        sql_referer_check = await result.fetchone()
        return bool(sql_referer_check)
