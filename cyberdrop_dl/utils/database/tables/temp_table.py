from __future__ import annotations

from typing import TYPE_CHECKING

from cyberdrop_dl.utils.database.table_definitions import create_temp

if TYPE_CHECKING:
    from aiosqlite import Connection


class TempTable:
    def __init__(self, db_conn: Connection) -> None:
        self.db_conn: Connection = db_conn

    async def startup(self) -> None:
        """Startup process for the TempTable."""
        await self.db_conn.execute(create_temp)
        await self.db_conn.commit()

    async def get_temp_names(self) -> list[str]:
        """Gets the list of temp filenames."""
        cursor = await self.db_conn.cursor()
        await cursor.execute("SELECT downloaded_filename FROM temp;")
        filenames = await cursor.fetchall()
        filenames = [list(filename) for filename in filenames]
        return list(sum(filenames, ()))

    async def sql_insert_temp(self, downloaded_filename: str) -> None:
        """Inserts a temp filename into the downloads_temp table."""
        await self.db_conn.execute("""INSERT OR IGNORE INTO downloads_temp VALUES (?)""", (downloaded_filename,))
        await self.db_conn.commit()
