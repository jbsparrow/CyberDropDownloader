from __future__ import annotations

import asyncio
from sqlite3 import IntegrityError, Row
from typing import TYPE_CHECKING

from cyberdrop_dl.database.base import HistoryTable
from cyberdrop_dl.utils.database.table_definitions import create_fixed_history, create_history
from cyberdrop_dl.utils.utilities import get_size_or_none, log

if TYPE_CHECKING:
    import datetime
    from collections.abc import Iterable

    import aiosqlite
    from yarl import URL

    from cyberdrop_dl.crawlers import Crawler
    from cyberdrop_dl.data_structures.url_objects import MediaItem
    from cyberdrop_dl.database.backends.sqlite import SQLiteDatabase
    from cyberdrop_dl.types import AbsoluteHttpURL


class SQliteHistoryTable(HistoryTable):
    def __init__(self, database: SQLiteDatabase) -> None:
        self.db: SQLiteDatabase = database
        self.name = "history"

    async def drop(self) -> None:
        async with self.db.get_transaction_cursor() as cursor:
            await cursor.execute(f"DROP TABLE IF EXISTS {self.name}")

    async def create(self) -> None:
        async with self.db.get_transaction_cursor() as cursor:
            await cursor.execute(create_history)
            await _fix_primary_keys(cursor)
            await _add_columns_media(cursor)
            await _fix_bunkr_v4_entries(cursor)
            await _run_updates(cursor)

    async def check_complete(self, domain: str, url: URL, referer: URL) -> bool:
        """Checks whether an individual file has completed given its domain and url path."""
        if self.db.ignore_history:
            return False

        url_path = get_db_path(url, domain)
        async with self.db.get_transaction_cursor() as cursor:
            query = """SELECT referer, completed FROM media WHERE domain = ? and url_path = ?"""
            await cursor.execute(query, (domain, url_path))
            sql_file_check = await cursor.fetchone()
            if sql_file_check and sql_file_check[1] != 0:
                # Update the referer if it has changed so that check_complete_from_referer can work
                referer_string = str(referer)
                if referer_string != sql_file_check[0] and url != referer:
                    log(f"Updating referer of {url} from {sql_file_check[0]} to {referer}")
                    query = """UPDATE media SET referer = ? WHERE domain = ? and url_path = ?"""
                    await cursor.execute(query, (referer_string, domain, url_path))
                return True
            return False

    async def check_album(self, domain: str, album_id: str) -> dict[str, int]:
        """Checks whether an album has completed given its domain and album id."""
        if self.db.ignore_history:
            return {}

        async with self.db.get_cursor() as cursor:
            query = """SELECT url_path, completed FROM media WHERE domain = ? and album_id = ?"""
            await cursor.execute(query, (domain, album_id))
            result = await cursor.fetchall()
            return {row[0]: row[1] for row in result}

    async def set_album_id(self, domain: str, media_item: MediaItem) -> None:
        async with self.db.get_transaction_cursor() as cursor:
            url_path = get_db_path(media_item.url, media_item.referer)
            query = """UPDATE media SET album_id = ? WHERE domain = ? and url_path = ?"""
            await cursor.execute(query, (media_item.album_id, domain, url_path))

    async def check_complete_by_referer(self, domain: str, referer: URL) -> bool:
        """Checks whether an individual file has completed given its domain and url path."""
        if self.db.ignore_history:
            return False

        async with self.db.get_cursor() as cursor:
            query = """SELECT completed FROM media WHERE domain = ? and referer = ?"""
            await cursor.execute(query, (domain, str(referer)))
            sql_file_check = await cursor.fetchone()
            return bool(sql_file_check and sql_file_check[0] != 0)

    async def insert_incompleted(self, domain: str, media_item: MediaItem) -> None:
        url_path = get_db_path(media_item.url, media_item.referer)
        download_filename = media_item.download_filename or ""
        query = """
        UPDATE media SET domain = ?, album_id = ? WHERE domain = 'no_crawler' and url_path = ? and referer = ?"""
        async with self.db.get_transaction_cursor() as cursor:
            try:
                await cursor.execute(query, (domain, media_item.album_id, url_path, str(media_item.referer)))
            except IntegrityError:
                query = """DELETE FROM media WHERE domain = 'no_crawler' and url_path = ?"""
                await cursor.execute(query, (url_path,))

        async with self.db.get_transaction_cursor() as cursor:
            query = """
            INSERT OR IGNORE INTO media (referer, download_path, original_filename, domain, url_path, album_id,
            download_filename,  completed, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)"""

            item_values = map(str, (media_item.referer, media_item.download_folder, media_item.original_filename))
            insert_values = (*item_values, domain, url_path, media_item.album_id, download_filename, 0)
            query = """UPDATE media SET download_filename = ? WHERE domain = ? and url_path = ?"""
            await cursor.execute(query, insert_values)
            if download_filename:
                await cursor.execute(query, (download_filename, domain, url_path))

    async def mark_complete(self, domain: str, media_item: MediaItem) -> None:
        url_path = get_db_path(media_item.url, media_item.referer)
        query = """UPDATE media SET completed = 1, completed_at = CURRENT_TIMESTAMP WHERE domain = ? and url_path = ?"""
        async with self.db.get_transaction_cursor() as cursor:
            await cursor.execute(query, (domain, url_path))

    async def add_filesize(self, domain: str, media_item: MediaItem) -> None:
        url_path = get_db_path(media_item.url, media_item.referer)
        file_size = await asyncio.to_thread(get_size_or_none, media_item.complete_file)
        query = """UPDATE media SET file_size=? WHERE domain = ? and url_path = ?"""
        async with self.db.get_transaction_cursor() as cursor:
            await cursor.execute(query, (file_size, domain, url_path))

    async def add_duration(self, domain: str, media_item: MediaItem) -> None:
        url_path = get_db_path(media_item.url, media_item.referer)
        duration = media_item.duration
        query = """UPDATE media SET duration=? WHERE domain = ? and url_path = ?"""
        async with self.db.get_transaction_cursor() as cursor:
            await cursor.execute(query, (duration, domain, url_path))

    async def get_duration(self, domain: str, media_item: MediaItem) -> float | None:
        if media_item.is_segment:
            return
        url_path = get_db_path(media_item.url, media_item.referer)
        query = """SELECT duration FROM media WHERE domain = ? and url_path = ?"""
        async with self.db.get_cursor() as cursor:
            await cursor.execute(query, (domain, url_path))
            sql_duration = await cursor.fetchone()
            return sql_duration[0] if sql_duration else None

    async def add_download_filename(self, domain: str, media_item: MediaItem) -> None:
        url_path = get_db_path(media_item.url, media_item.referer)
        query = """UPDATE media SET download_filename=? WHERE domain = ? and url_path = ? and download_filename = '' """
        async with self.db.get_transaction_cursor() as cursor:
            await cursor.execute(query, (media_item.download_filename, domain, url_path))

    async def check_filename_exists(self, filename: str) -> bool:
        query = """SELECT EXISTS(SELECT 1 FROM media WHERE download_filename = ?)"""
        async with self.db.get_cursor() as cursor:
            await cursor.execute(query, (filename,))
            sql_file_check = await cursor.fetchone()
            return sql_file_check == 1

    async def get_downloaded_filename(self, domain: str, media_item: MediaItem) -> str | None:
        url_path = get_db_path(media_item.url, media_item.referer)
        query = """SELECT download_filename FROM media WHERE domain = ? and url_path = ?"""
        async with self.db.get_cursor() as cursor:
            await cursor.execute(query, (domain, url_path))
            sql_file_check = await cursor.fetchone()
            return sql_file_check[0] if sql_file_check else None

    async def get_failed_items(self) -> Iterable[Row]:
        query = """SELECT referer, download_path,completed_at,created_at FROM media WHERE completed = 0"""
        async with self.db.get_cursor() as cursor:
            await cursor.execute(query)
            return await cursor.fetchall()

    async def get_all_items(self, after: datetime.date, before: datetime.date) -> Iterable[Row]:
        """Returns a list of all items."""

        date_format = "%Y-%m-%d"
        query = """
        SELECT referer, download_path,completed_at,created_at
        FROM media
        WHERE COALESCE(completed_at, '1970-01-01') BETWEEN ? AND ?
        ORDER BY completed_at DESC;"""
        async with self.db.get_cursor() as cursor:
            await cursor.execute(query, (after.strftime(date_format), before.strftime(date_format)))
            return await cursor.fetchall()

    async def get_all_bunkr_failed(self) -> list[tuple[str, str, str, str]]:
        query_size = """SELECT referer, download_path, completed_at, created_at from media where file_size=322509;"""
        query_hash = """SELECT m.referer, download_path,c ompleted_at, created_at FROM hash h
        INNER JOIN media m ON h.download_filename= m.download_filename WHERE h.hash = 'eb669b6362e031fa2b0f1215480c4e30';"""
        results = []
        async with self.db.get_cursor() as cursor:
            try:
                for query in (query_size, query_hash):
                    await cursor.execute(query)
                    files = await cursor.fetchall()
                    results.append(list(files))
            except Exception as e:
                log(f"Error getting bunkr failed files: {e}", 40, exc_info=e)
                return []
            else:
                return results


async def _fix_bunkr_v4_entries(cursor: aiosqlite.Cursor) -> None:
    query = """SELECT * from media WHERE domain = 'bunkr' and completed = 1"""
    await cursor.execute(query)
    bunkr_entries = await cursor.fetchall()
    query = """INSERT or REPLACE INTO media VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?,?)"""
    for entry in bunkr_entries:
        entry_list = list(entry)
        entry_list[0] = "bunkrr"
        await cursor.execute(query, entry_list)

    query = """DELETE FROM media WHERE domain = 'bunkr'"""
    await cursor.execute(query)


async def _fix_primary_keys(cursor: aiosqlite.Cursor) -> None:
    await cursor.execute("""pragma table_info(media)""")
    result = await cursor.fetchall()
    query = """
    INSERT INTO media_copy (domain, url_path, referer, download_path, download_filename, original_filename, completed)
    SELECT * FROM media GROUP BY domain, url_path, original_filename;
    DROP TABLE media;
    ALTER TABLE media_copy RENAME TO media;"""
    if result[0][5] == 0:  # type: ignore
        await cursor.execute(create_fixed_history)
        await cursor.executescript(query)


async def _add_columns_media(cursor: aiosqlite.Cursor) -> None:
    query = """pragma table_info(media)"""
    await cursor.execute(query)
    result = await cursor.fetchall()
    current_cols: list[str] = [col[1] for col in result]

    check_columns = [
        ("album_id", "TEXT"),
        ("created_at", "TIMESTAMP"),
        ("completed_at", "TIMESTAMP"),
        ("file_size", "INT"),
        ("duration", "FLOAT"),
    ]

    for col in check_columns:
        name, type = col
        if name not in current_cols:
            query = f"ALTER TABLE media ADD COLUMN {name} {type}"
            await cursor.execute(query)


async def _run_updates(cursor: aiosqlite.Cursor) -> None:
    query = """
    UPDATE OR REPLACE media SET domain = 'jpg5.su' WHERE domain = 'sharex';
    UPDATE OR REPLACE media SET domain = 'nudostar.tv' WHERE domain = 'nudostartv';
    DELETE FROM media WHERE download_filename = '';"""
    await cursor.executescript(query)


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


async def update_previously_unsupported(cursor: aiosqlite.Cursor, crawlers: dict[str, Crawler]) -> None:
    """Update old `no_crawler` entries that are now supported."""
    domains_to_update = [
        (c.domain, f"http%{c.primary_base_domain.host}%") for c in crawlers.values() if c.update_unsupported
    ]
    if not domains_to_update:
        return

    referers = [(d[1],) for d in domains_to_update]
    query = "UPDATE OR IGNORE media SET domain = ? WHERE domain = 'no_crawler' AND referer LIKE ?"
    await cursor.executemany(query, domains_to_update)
    query = "DELETE FROM media WHERE domain = 'no_crawler' AND referer LIKE ?"
    await cursor.executemany(query, referers)
