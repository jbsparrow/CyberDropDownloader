from __future__ import annotations

from typing import TYPE_CHECKING

from cyberdrop_dl.utils.database.table_definitions import create_temp_referer

if TYPE_CHECKING:
    import aiosqlite
    from yarl import URL

db_conn: aiosqlite.Connection
_ignore_history: bool


async def startup(db_conn: aiosqlite.Connection, ignore_history: bool = False) -> None:
    global _db_conn, _ignore_history
    _db_conn: aiosqlite.Connection = db_conn
    _ignore_history: bool = ignore_history
    await _db_conn.execute(create_temp_referer)
    await _db_conn.commit()


async def get_temp_referers() -> list[str]:
    cursor = await _db_conn.cursor()
    await cursor.execute("SELECT referer FROM temp_referer;")
    referers = await cursor.fetchall()
    referers = [list(referer) for referer in referers]
    return list(sum(referers, ()))


async def sql_insert_temp_referer(referer: str) -> None:
    await _db_conn.execute("""INSERT OR IGNORE INTO temp_referer VALUES (?)""", (referer,))
    await _db_conn.commit()


async def sql_purge_temp_referers() -> None:
    await _db_conn.execute("""DELETE FROM temp_referer;""")
    await _db_conn.commit()


async def sql_drop_temp_referers() -> None:
    await _db_conn.execute("""DROP TABLE IF EXISTS temp_referer""")
    await _db_conn.commit()


async def check_referer(referer: URL) -> bool:
    """Checks whether an individual referer url has already been recorded in the database."""
    if _ignore_history:
        return False

    referer_str = str(referer)

    cursor = await _db_conn.cursor()
    result = await cursor.execute("""SELECT url_path FROM media WHERE referer = ? """, (referer_str,))
    sql_referer_check = await result.fetchone()
    sql_referer_check_current_run = await _check_temp_referer(referer)
    if not sql_referer_check:
        await sql_insert_temp_referer(referer_str)
        return False
    return not sql_referer_check_current_run


async def _check_temp_referer(referer: URL) -> bool:
    """Checks whether an individual referer url has already been recorded in this session."""
    if _ignore_history:
        return False

    referer_str = str(referer)
    cursor = await _db_conn.cursor()
    result = await cursor.execute("""SELECT referer FROM temp_referer WHERE referer = ? """, (referer_str,))
    sql_referer_check = await result.fetchone()
    return bool(sql_referer_check)
