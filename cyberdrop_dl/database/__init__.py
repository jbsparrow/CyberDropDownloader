from cyberdrop_dl.database.base import DBBackend


def delay_import_error(exception: Exception) -> type[DBBackend]:
    class NotFoundBackend:
        def __init__(*args, **kwargs) -> None:
            raise exception

    return NotFoundBackend  # type: ignore


from cyberdrop_dl.database.backends.sqlite import SQLiteDatabase

try:
    from cyberdrop_dl.database.backends.postgres import PostgresDatabase
except ImportError as e:
    PostgresDatabase = delay_import_error(e)


__all__ = ["PostgresDatabase", "SQLiteDatabase"]
