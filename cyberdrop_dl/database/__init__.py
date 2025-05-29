from pathlib import Path

from cyberdrop_dl.database.base import Database, HashTable, HistoryTable, TempRefererTable


def delay_import_error(exception: Exception) -> type[Database]:
    class NotFoundBackend:
        def __init__(*args, **kwargs) -> None:
            raise exception

    return NotFoundBackend  # type: ignore


from cyberdrop_dl.database.backends.sqlite import SQLiteDatabase

try:
    from cyberdrop_dl.database.backends.postgres import PostgresDatabase
except ImportError as e:
    PostgresDatabase = delay_import_error(e)

_database: Database = None  # type: ignore
# re-export tables for easy access
hash_table: HashTable
history_table: HistoryTable
temp_referer_table: TempRefererTable


def startup(db_path: Path, ignore_history: bool = False) -> None:
    global _database
    assert not _database
    _database = SQLiteDatabase(db_path, ignore_history)


async def connect() -> None:
    global hash_table, history_table, temp_referer_table
    await _database.connect()
    hash_table = _database.hash_table
    history_table = _database.history_table
    temp_referer_table = _database.temp_referer_table


async def close() -> None:
    global _database, hash_table, history_table, temp_referer_table
    await _database.close()
    del hash_table, history_table, temp_referer_table
    _database = None  # type: ignore


__all__ = ["close", "connect", "startup"]
