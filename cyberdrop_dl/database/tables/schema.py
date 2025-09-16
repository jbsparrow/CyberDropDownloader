from __future__ import annotations

from typing import TYPE_CHECKING

import aiosqlite
from packaging.version import Version

from cyberdrop_dl.utils.logger import log, log_spacer

from .definitions import create_schema_version

if TYPE_CHECKING:
    import aiosqlite

    from cyberdrop_dl.database import Database


CURRENT_APP_SCHEMA_VERSION = "8.0.0"


class SchemaVersionTable:
    def __init__(self, database: Database) -> None:
        self._database = database

    @property
    def db_conn(self) -> aiosqlite.Connection:
        return self._database._db_conn

    async def get_version(self) -> Version | None:
        if not await self.__exists():
            return
        query = "SELECT version FROM schema_version;"
        cursor = await self.db_conn.execute(query)
        result = await cursor.fetchone()
        if result:
            return Version(result["version"])

    async def __exists(self) -> bool:
        query = "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version';"
        cursor = await self.db_conn.execute(query)
        result = await cursor.fetchone()
        return result is not None

    async def __create_if_not_exists(self) -> None:
        await self.db_conn.execute(create_schema_version)
        await self.db_conn.commit()

    async def __update_schema_version(self) -> None:
        await self.__create_if_not_exists()
        query = "INSERT INTO schema_version (version) VALUES (?)"
        await self.db_conn.execute(query, (CURRENT_APP_SCHEMA_VERSION,))
        await self.db_conn.commit()

    async def startup(self) -> None:
        log_spacer(10)
        log(f"Expected database schema version: {CURRENT_APP_SCHEMA_VERSION}")
        version = await self.get_version()
        log(f"Database reports installed version: {version}")
        if version is not None and version >= Version(CURRENT_APP_SCHEMA_VERSION):
            return

        # TODO: on v9, raise SystemExit if db version is None or older than 8.0.0
        log(f"Updating database version to {CURRENT_APP_SCHEMA_VERSION}")
        await self.__update_schema_version()
