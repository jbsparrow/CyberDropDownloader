from __future__ import annotations

from typing import TYPE_CHECKING

from cyberdrop_dl.database.base import TempRefererTable
from cyberdrop_dl.utils.database.table_definitions import create_temp_referer

if TYPE_CHECKING:
    from cyberdrop_dl.database.backends.sqlite import SQLiteDatabase
    from cyberdrop_dl.types import AbsoluteHttpURL


class SQliteTempRefererTable(TempRefererTable):
    def __init__(self, database: SQLiteDatabase) -> None:
        self.db: SQLiteDatabase = database

    async def create(self) -> None:
        async with self.db.get_transaction_cursor() as cursor:
            await cursor.execute(create_temp_referer)

    async def check_referer(self, referer: AbsoluteHttpURL) -> bool:
        """Checks whether an individual referer url has already been recorded in the database."""
        if self.db.ignore_history:
            return False

        params = (str(referer),)
        async with self.db.get_transaction_cursor() as cursor:
            await cursor.execute("""SELECT url_path FROM media WHERE referer = ? """, params)
            referer_exists = bool(await cursor.fetchone())
            await cursor.execute("""SELECT referer FROM temp_referer WHERE referer = ? """, params)
            referer_current_run_exists = bool(await cursor.fetchone())
            if not referer_exists:
                await cursor.execute("""INSERT OR IGNORE INTO temp_referer VALUES (?)""", params)
                return False
            return not referer_current_run_exists
