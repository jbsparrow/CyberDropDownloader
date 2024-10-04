from typing import List

import aiosqlite

from cyberdrop_dl.utils.database.table_definitions import create_temp_referer


class TempRefererTable:
    def __init__(self, db_conn: aiosqlite.Connection):
        self.db_conn: aiosqlite.Connection = db_conn

    async def startup(self) -> None:
        """Startup process for the TempRefererTable"""
        await self.db_conn.execute(create_temp_referer)
        await self.db_conn.commit()

    async def get_temp_referers(self) -> List[str]:
        """Gets the list of temp referers"""
        cursor = await self.db_conn.cursor()
        await cursor.execute("SELECT referer FROM temp_referer;")
        referers = await cursor.fetchall()
        referers = [list(referer) for referer in referers]
        return list(sum(referers, ()))

    async def sql_insert_temp_referer(self, referer: str) -> None:
        """Inserts a temp referer into the temp_referers table"""
        await self.db_conn.execute("""INSERT OR IGNORE INTO temp_referer VALUES (?)""", (referer,))
        await self.db_conn.commit()

    async def sql_purge_temp_referers(self) -> None:
        """Delete all records in temp_referers table"""
        await self.db_conn.execute("""DELETE FROM temp_referer;""")
        await self.db_conn.commit()

    async def sql_drop_temp_referers(self) -> None:
        """Delete temp_referers table"""
        await self.db_conn.execute("""DROP TABLE temp_referer;""")
        await self.db_conn.commit()
