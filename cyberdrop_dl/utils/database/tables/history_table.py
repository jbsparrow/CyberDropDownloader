from __future__ import annotations

import asyncio
from sqlite3 import IntegrityError, Row
from typing import TYPE_CHECKING

from cyberdrop_dl.utils.database.table_definitions import create_fixed_history, create_history
from cyberdrop_dl.utils.utilities import get_size_or_none, log

if TYPE_CHECKING:
    import datetime
    from collections.abc import Iterable

    import aiosqlite
    from yarl import URL

    from cyberdrop_dl.crawlers import Crawler
    from cyberdrop_dl.data_structures.url_objects import MediaItem
    from cyberdrop_dl.types import AbsoluteHttpURL


def get_db_path(url: URL, referer: str | AbsoluteHttpURL = "") -> str:
    """Gets the URL path to be put into the DB and checked from the DB."""
    url_path = url.path
    referer = str(referer)
    if referer:
        if "e-hentai" in referer:
            url_path = url_path.split("keystamp")[0][:-1]
        elif "mediafire" in referer:
            url_path = url.name

    return url_path


_db_conn: aiosqlite.Connection
_ignore_history: bool


async def startup(db_conn: aiosqlite.Connection, ignore_history: bool = False) -> None:
    global _db_conn, _ignore_history
    _db_conn = db_conn
    _ignore_history: bool = ignore_history
    await _db_conn.execute(create_history)
    await _db_conn.commit()
    await fix_primary_keys()
    await add_columns_media()
    await fix_bunkr_v4_entries()
    await run_updates()


async def update_previously_unsupported(crawlers: dict[str, Crawler]) -> None:
    """Update old `no_crawler` entries that are now supported."""
    domains_to_update = [
        (c.domain, f"http%{c.primary_base_domain.host}%") for c in crawlers.values() if c.update_unsupported
    ]
    if not domains_to_update:
        return
    referers = [(d[1],) for d in domains_to_update]
    cursor = await _db_conn.cursor()
    query = "UPDATE OR IGNORE media SET domain = ? WHERE domain = 'no_crawler' AND referer LIKE ?"
    await cursor.executemany(query, domains_to_update)
    query = "DELETE FROM media WHERE domain = 'no_crawler' AND referer LIKE ?"
    await cursor.executemany(query, referers)
    await _db_conn.commit()


async def run_updates() -> None:
    cursor = await _db_conn.cursor()
    query = """UPDATE OR REPLACE media SET domain = 'jpg5.su' WHERE domain = 'sharex'"""
    await cursor.execute(query)
    query = """UPDATE OR REPLACE media SET domain = 'nudostar.tv' WHERE domain = 'nudostartv'"""
    await cursor.execute(query)
    await _db_conn.commit()


async def delete_invalid_rows() -> None:
    query = """DELETE FROM media WHERE download_filename = '' """
    cursor = await _db_conn.cursor()
    await cursor.execute(query)
    await _db_conn.commit()


async def check_complete(domain: str, url: URL, referer: URL) -> bool:
    """Checks whether an individual file has completed given its domain and url path."""
    if _ignore_history:
        return False

    url_path = get_db_path(url, domain)
    cursor = await _db_conn.cursor()
    query = """SELECT referer, completed FROM media WHERE domain = ? and url_path = ?"""
    result = await cursor.execute(query, (domain, url_path))
    sql_file_check = await result.fetchone()
    if sql_file_check and sql_file_check[1] != 0:
        # Update the referer if it has changed so that check_complete_from_referer can work
        if str(referer) != sql_file_check[0] and url != referer:
            log(f"Updating referer of {url} from {sql_file_check[0]} to {referer}")
            query = """UPDATE media SET referer = ? WHERE domain = ? and url_path = ?"""
            await cursor.execute(query, (str(referer), domain, url_path))
            await _db_conn.commit()

        return True
    return False


async def check_album(domain: str, album_id: str) -> dict[str, int]:
    """Checks whether an album has completed given its domain and album id."""
    if _ignore_history:
        return {}

    query = """SELECT url_path, completed FROM media WHERE domain = ? and album_id = ?"""
    cursor = await _db_conn.cursor()
    result = await cursor.execute(query, (domain, album_id))
    result = await result.fetchall()
    return {row[0]: row[1] for row in result}


async def set_album_id(domain: str, media_item: MediaItem) -> None:
    url_path = get_db_path(media_item.url, media_item.referer)
    query = """UPDATE media SET album_id = ? WHERE domain = ? and url_path = ?"""
    await _db_conn.execute(query, (media_item.album_id, domain, url_path))
    await _db_conn.commit()


async def check_complete_by_referer(domain: str, referer: URL) -> bool:
    """Checks whether an individual file has completed given its domain and url path."""
    if _ignore_history:
        return False

    query = """SELECT completed FROM media WHERE domain = ? and referer = ?"""
    cursor = await _db_conn.cursor()
    result = await cursor.execute(query, (domain, str(referer)))
    sql_file_check = await result.fetchone()
    return bool(sql_file_check and sql_file_check[0] != 0)


async def insert_incompleted(domain: str, media_item: MediaItem) -> None:
    url_path = get_db_path(media_item.url, media_item.referer)
    download_filename = media_item.download_filename or ""
    query = """UPDATE media SET domain = ?, album_id = ? WHERE domain = 'no_crawler' and url_path = ? and referer = ?"""
    try:
        await _db_conn.execute(query, (domain, media_item.album_id, url_path, str(media_item.referer)))
    except IntegrityError:
        query = """DELETE FROM media WHERE domain = 'no_crawler' and url_path = ?"""
        await _db_conn.execute(query, (url_path,))

    query = """INSERT OR IGNORE INTO media (referer, download_path, original_filename, domain, url_path, album_id,
    download_filename,  completed, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)"""

    item_values = map(str, (media_item.referer, media_item.download_folder, media_item.original_filename))
    insert_values = (*item_values, domain, url_path, media_item.album_id, download_filename, 0)
    query = """UPDATE media SET download_filename = ? WHERE domain = ? and url_path = ?"""
    await _db_conn.execute(query, insert_values)
    if download_filename:
        await _db_conn.execute(query, (download_filename, domain, url_path))
    await _db_conn.commit()


async def mark_complete(domain: str, media_item: MediaItem) -> None:
    url_path = get_db_path(media_item.url, media_item.referer)
    query = ("""UPDATE media SET completed = 1, completed_at = CURRENT_TIMESTAMP WHERE domain = ? and url_path = ?""",)
    await _db_conn.execute(query, (domain, url_path))
    await _db_conn.commit()


async def add_filesize(domain: str, media_item: MediaItem) -> None:
    url_path = get_db_path(media_item.url, media_item.referer)
    file_size = await asyncio.to_thread(get_size_or_none, media_item.complete_file)
    query = """UPDATE media SET file_size=? WHERE domain = ? and url_path = ?"""
    await _db_conn.execute(query, (file_size, domain, url_path))
    await _db_conn.commit()


async def add_duration(domain: str, media_item: MediaItem) -> None:
    url_path = get_db_path(media_item.url, media_item.referer)
    duration = media_item.duration
    query = """UPDATE media SET duration=? WHERE domain = ? and url_path = ?"""
    await _db_conn.execute(query, (duration, domain, url_path))
    await _db_conn.commit()


async def get_duration(domain: str, media_item: MediaItem) -> float | None:
    if media_item.is_segment:
        return
    url_path = get_db_path(media_item.url, media_item.referer)
    query = """SELECT duration FROM media WHERE domain = ? and url_path = ?"""
    cursor = await _db_conn.cursor()
    result = await cursor.execute(query, (domain, url_path))
    sql_duration = await result.fetchone()
    return sql_duration[0] if sql_duration else None


async def add_download_filename(domain: str, media_item: MediaItem) -> None:
    url_path = get_db_path(media_item.url, media_item.referer)
    query = """UPDATE media SET download_filename=? WHERE domain = ? and url_path = ? and download_filename = '' """
    await _db_conn.execute(query, (media_item.download_filename, domain, url_path))
    await _db_conn.commit()


async def check_filename_exists(filename: str) -> bool:
    cursor = await _db_conn.cursor()
    query = """SELECT EXISTS(SELECT 1 FROM media WHERE download_filename = ?)"""
    result = await cursor.execute(query, (filename,))
    sql_file_check = await result.fetchone()
    return sql_file_check == 1


async def get_downloaded_filename(domain: str, media_item: MediaItem) -> str | None:
    url_path = get_db_path(media_item.url, media_item.referer)
    cursor = await _db_conn.cursor()
    query = """SELECT download_filename FROM media WHERE domain = ? and url_path = ?"""
    result = await cursor.execute(query, (domain, url_path))
    sql_file_check = await result.fetchone()
    return sql_file_check[0] if sql_file_check else None


async def get_failed_items() -> Iterable[Row]:
    cursor = await _db_conn.cursor()
    query = """SELECT referer, download_path,completed_at,created_at FROM media WHERE completed = 0"""
    result = await cursor.execute(query)
    return await result.fetchall()


async def get_all_items(after: datetime.date, before: datetime.date) -> Iterable[Row]:
    """Returns a list of all items."""
    cursor = await _db_conn.cursor()
    date_format = "%Y-%m-%d"
    query = """
    SELECT referer, download_path,completed_at,created_at
    FROM media
    WHERE COALESCE(completed_at, '1970-01-01') BETWEEN ? AND ?
    ORDER BY completed_at DESC;"""
    result = await cursor.execute(query, (after.strftime(date_format), before.strftime(date_format)))
    return await result.fetchall()


async def get_unique_download_paths() -> Iterable[Row]:
    cursor = await _db_conn.cursor()
    query = """SELECT DISTINCT download_path FROM media"""
    result = await cursor.execute(query)
    return await result.fetchall()


async def get_all_bunkr_failed() -> list[tuple[str, str, str, str]]:
    query_size = """SELECT referer, download_path, completed_at, created_at from media where file_size=322509;"""
    query_hash = """SELECT m.referer, download_path,c ompleted_at, created_at FROM hash h
    INNER JOIN media m ON h.download_filename= m.download_filename WHERE h.hash = 'eb669b6362e031fa2b0f1215480c4e30';"""
    cursor = await _db_conn.cursor()
    all_results = []
    try:
        for query in (query_size, query_hash):
            result = await cursor.execute(query)
            all_files = await result.fetchall()
            all_results.append(list(all_files))
    except Exception as e:
        log(f"Error getting bunkr failed files: {e}", 40, exc_info=e)
        return []
    else:
        return all_results


async def fix_bunkr_v4_entries() -> None:
    cursor = await _db_conn.cursor()
    query = """SELECT * from media WHERE domain = 'bunkr' and completed = 1"""
    result = await cursor.execute(query)
    bunkr_entries = await result.fetchall()
    query = """INSERT or REPLACE INTO media VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?,?)"""
    for entry in bunkr_entries:
        entry_list = list(entry)
        entry_list[0] = "bunkrr"
        await _db_conn.execute(query, entry_list)

    query = """DELETE FROM media WHERE domain = 'bunkr'"""
    await _db_conn.commit()
    await _db_conn.execute(query)
    await _db_conn.commit()


async def fix_primary_keys() -> None:
    cursor = await _db_conn.cursor()
    result = await cursor.execute("""pragma table_info(media)""")
    result = await result.fetchall()
    query = """INSERT INTO media_copy (domain, url_path, referer, download_path, download_filename, original_filename, completed)
    SELECT * FROM media GROUP BY domain, url_path, original_filename;"""
    if result[0][5] == 0:  # type: ignore
        await _db_conn.execute(create_fixed_history)
        await _db_conn.commit()
        await _db_conn.execute(query)
        await _db_conn.commit()
        query = """DROP TABLE media"""
        await _db_conn.execute(query)
        await _db_conn.commit()
        query = """ALTER TABLE media_copy RENAME TO media"""
        await _db_conn.execute(query)
        await _db_conn.commit()


async def add_columns_media() -> None:
    cursor = await _db_conn.cursor()
    query = """pragma table_info(media)"""
    result = await cursor.execute(query)
    result = await result.fetchall()
    current_cols: list[str] = [col[1] for col in result]

    check_columns = [
        ("album_id", "TEXT"),
        ("created_at", "TIMESTAMP"),
        ("completed_at", "TIMESTAMP"),
        ("file_size", "INT"),
        ("duration", "FLOAT"),
    ]

    for col in check_columns:
        if col[0] not in current_cols:
            query = f"ALTER TABLE media ADD COLUMN {col[0]} {col[1]}"
            await _db_conn.execute(query)
            await _db_conn.commit()
