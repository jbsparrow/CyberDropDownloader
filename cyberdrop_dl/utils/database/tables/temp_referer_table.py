from typing import List

import aiosqlite
from yarl import URL
from cyberdrop_dl.utils.database.table_definitions import create_temp_referer


class TempRefererTable:
    def __init__(self, db_conn: aiosqlite.Connection):
        self.db_conn: aiosqlite.Connection = db_conn
        self.ignore_history: bool = False

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
        await self.db_conn.execute("""DROP TABLE IF EXISTS temp_referer""")
        await self.db_conn.commit()

    async def check_referer(self, referer: URL) -> bool:
        """Checks whether an individual referer url has already been recorded in the database"""
        if self.ignore_history:
            return False
        
        referer = str(referer)

        cursor = await self.db_conn.cursor()
        result = await cursor.execute("""SELECT url_path FROM media WHERE referer = ? """,
                                    (referer,))
        sql_referer_check = await result.fetchone()
        sql_referer_check_current_run = await self._check_temp_referer(referer)
        if not sql_referer_check:
            await self.sql_insert_temp_referer(referer)
            return False
        elif sql_referer_check_current_run:
            return False
        return True
    
    async def _check_temp_referer(self, referer: URL) -> bool:
        """Checks whether an individual referer url has already been recorded in this session"""
        if self.ignore_history:
            return False

        referer = str(referer)
        cursor = await self.db_conn.cursor()
        result = await cursor.execute("""SELECT referer FROM temp_referer WHERE referer = ? """,
                                    (referer,))
        sql_referer_check = await result.fetchone()
        if sql_referer_check:
            return True
        return False
