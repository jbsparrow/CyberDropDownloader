import psycopg  # type: ignore # noqa: F401

from cyberdrop_dl.database.base import DBBackend


class PostgresDatabase(DBBackend): ...
