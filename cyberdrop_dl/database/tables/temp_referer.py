from __future__ import annotations

from typing import TYPE_CHECKING

from .definitions import create_temp_referer

if TYPE_CHECKING:
    import aiosqlite
    from yarl import URL

    from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
    from cyberdrop_dl.database import Database


class TempRefererTable:
    def __init__(self, database: Database) -> None:
        self._database = database

    @property
    def db_conn(self) -> aiosqlite.Connection:
        return self._database._db_conn

    async def startup(self) -> None:
        """Startup process for the TempRefererTable."""
        await self.db_conn.execute(create_temp_referer)
        await self.db_conn.commit()

    async def get_temp_referers(self) -> list[str]:
        """Gets the list of temp referrer."""
        query = "SELECT referer FROM temp_referer;"
        cursor = await self.db_conn.execute(query)
        rows = await cursor.fetchall()
        return [row[0] for row in rows]

    async def sql_insert_temp_referer(self, referer: str) -> None:
        """Inserts a temp referer into the temp_referers table."""
        query = "INSERT OR IGNORE INTO temp_referer VALUES (?)"
        await self.db_conn.execute(query, (referer,))
        await self.db_conn.commit()

    async def sql_purge_temp_referers(self) -> None:
        """Delete all records in temp_referers table."""
        query = "DELETE FROM temp_referer;"
        await self.db_conn.execute(query)
        await self.db_conn.commit()

    async def sql_drop_temp_referers(self) -> None:
        """Delete temp_referers table."""
        query = "DROP TABLE IF EXISTS temp_referer"
        await self.db_conn.execute(query)
        await self.db_conn.commit()

    async def check_referer(self, referer: AbsoluteHttpURL) -> bool:
        """Checks whether an individual referer url has already been recorded in the database."""
        if self._database.ignore_history:
            return False

        referer_str = str(referer)

        # TODO: This logic is broken
        query = "SELECT url_path FROM media WHERE referer = ?"
        cursor = await self.db_conn.execute(query, (referer_str,))
        in_media_table = await cursor.fetchone()
        in_temp_referer = await self._check_temp_referer(referer)
        if not in_media_table:
            await self.sql_insert_temp_referer(referer_str)
            return False

        return not in_temp_referer

    async def _check_temp_referer(self, referer: URL) -> bool:
        """Checks whether an individual referer url has already been recorded in this session."""
        if self._database.ignore_history:
            return False

        query = "SELECT referer FROM temp_referer WHERE referer = ?"
        cursor = await self.db_conn.execute(query, (str(referer),))
        return bool(await cursor.fetchone())
