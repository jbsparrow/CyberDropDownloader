from __future__ import annotations

from sqlite3 import IntegrityError, Row
from typing import TYPE_CHECKING, cast

from cyberdrop_dl.data_structures.url_objects import MediaItem
from cyberdrop_dl.utils.utilities import log

from .definitions import create_fixed_history, create_history

if TYPE_CHECKING:
    import datetime
    from collections.abc import AsyncGenerator

    import aiosqlite
    from yarl import URL

    from cyberdrop_dl.crawlers import Crawler
    from cyberdrop_dl.database import Database


_FETCH_MANY_SIZE: int = 1000


class HistoryTable:
    def __init__(self, database: Database) -> None:
        self._database = database

    @property
    def db_conn(self) -> aiosqlite.Connection:
        return self._database._db_conn

    async def startup(self) -> None:
        """Startup process for the HistoryTable."""
        from cyberdrop_dl.crawlers import jpg5, redgifs

        await self.db_conn.create_function("FIX_REDGIFS_REFERER", 1, redgifs.fix_db_referer, deterministic=True)
        await self.db_conn.create_function("FIX_JPG5_REFERER", 1, jpg5.fix_db_referer, deterministic=True)
        await self.db_conn.execute(create_history)
        await self.db_conn.commit()
        await self.fix_primary_keys()
        await self.add_columns_media()
        await self.run_updates()

    async def update_previously_unsupported(self, crawlers: dict[str, Crawler]) -> None:
        """Update old `no_crawler` entries that are now supported."""
        domains_to_update = {
            crawler.DOMAIN: f"http%{crawler.PRIMARY_URL.host}%"
            for crawler in crawlers.values()
            if crawler.UPDATE_UNSUPPORTED
        }
        if not domains_to_update:
            return

        query = "UPDATE OR IGNORE media SET domain = ? WHERE domain = 'no_crawler' AND referer LIKE ?"
        cursor = await self.db_conn.executemany(query, domains_to_update.items())
        query = "DELETE FROM media WHERE domain = 'no_crawler' AND referer LIKE ?"
        await cursor.executemany(query, [[x] for x in domains_to_update.values()])
        await self.db_conn.commit()

    async def run_updates(self) -> None:
        updates = (
            "UPDATE OR REPLACE media SET domain = 'jpg5.su' WHERE domain = 'sharex';"
            "UPDATE OR REPLACE media SET domain = 'nudostar.tv' WHERE domain = 'nudostartv';"
            "UPDATE OR REPLACE media SET referer = FIX_REDGIFS_REFERER(referer) WHERE domain = 'redgifs';"
            "UPDATE OR REPLACE media SET referer = FIX_JPG5_REFERER(referer) WHERE domain = 'jpg5.su';"
        )

        await self.db_conn.executescript(updates)
        await self.db_conn.commit()

    async def delete_invalid_rows(self) -> None:
        query = "DELETE FROM media WHERE download_filename = '' "
        await self.db_conn.execute(query)
        await self.db_conn.commit()

    async def check_complete(self, domain: str, url: URL, referer: URL) -> bool:
        """Checks whether an individual file has completed given its domain and url path."""
        if self._database.ignore_history:
            return False

        url_path = MediaItem.create_db_path(url, domain)

        async def select_referer_and_completed() -> tuple[str, bool]:
            query = "SELECT referer, completed FROM media WHERE domain = ? and url_path = ?"
            cursor = await self.db_conn.execute(query, (domain, url_path))
            if row := await cursor.fetchone():
                return row[0], row[1]
            return "", False

        async def update_referer() -> None:
            query = "UPDATE media SET referer = ? WHERE domain = ? and url_path = ?"
            await self.db_conn.execute(query, (str(referer), domain, url_path))
            await self.db_conn.commit()

        current_referer, completed = await select_referer_and_completed()
        if completed and url != referer and str(referer) != current_referer:
            # Update the referer if it has changed so that check_complete_by_referer can work
            log(f"Updating referer of {url} from {current_referer} to {referer}")
            await update_referer()

        return completed

    async def check_album(self, domain: str, album_id: str) -> dict[str, int]:
        """Checks whether an album has completed given its domain and album id."""
        if self._database.ignore_history:
            return {}

        query = "SELECT url_path, completed FROM media WHERE domain = ? and album_id = ?"
        cursor = await self.db_conn.execute(query, (domain, album_id))
        rows = await cursor.fetchall()
        return {row[0]: row[1] for row in rows}

    async def set_album_id(self, domain: str, media_item: MediaItem) -> None:
        """Sets an album_id in the database."""

        query = "UPDATE media SET album_id = ? WHERE domain = ? and url_path = ?"
        await self.db_conn.execute(query, (media_item.album_id, domain, media_item.db_path))
        await self.db_conn.commit()

    async def check_complete_by_referer(self, domain: str | None, referer: URL) -> bool:
        """Checks whether an individual file has completed given its domain and url path."""
        if self._database.ignore_history:
            return False

        if domain is None:
            query = "SELECT completed FROM media WHERE referer = ?"
            params = (str(referer),)
        else:
            query = "SELECT completed FROM media WHERE referer = ? and domain = ?"
            params = str(referer), domain

        cursor = await self.db_conn.execute(query, params)
        if domain is None:
            rows = await cursor.fetchall()
        else:
            row = await cursor.fetchone()
            if row is None:
                return False
            rows = [row]
        return bool(rows and any(row[0] != 0 for row in rows))

    async def insert_incompleted(self, domain: str, media_item: MediaItem) -> None:
        """Inserts an uncompleted file into the database."""

        url_path = media_item.db_path
        download_filename = media_item.download_filename or ""
        cursor = await self.db_conn.cursor()
        query = "UPDATE media SET domain = ?, album_id = ? WHERE domain = 'no_crawler' and url_path = ? and referer = ?"
        try:
            await cursor.execute(query, (domain, media_item.album_id, url_path, str(media_item.referer)))
        except IntegrityError:
            delete_query = "DELETE FROM media WHERE domain = 'no_crawler' and url_path = ?"
            await cursor.execute(delete_query, (url_path,))

        insert_query = """
        INSERT OR IGNORE INTO media (domain, url_path, referer, album_id, download_path,
        download_filename, original_filename, completed, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP);
        """

        await cursor.execute(
            insert_query,
            (
                domain,
                url_path,
                str(media_item.referer),
                media_item.album_id,
                str(media_item.download_folder),
                download_filename,
                media_item.original_filename,
                0,
            ),
        )
        if download_filename:
            query = "UPDATE media SET download_filename = ? WHERE domain = ? and url_path = ?"
            await cursor.execute(query, (download_filename, domain, url_path))
        await self.db_conn.commit()

    async def mark_complete(self, domain: str, media_item: MediaItem) -> None:
        """Mark a download as completed in the database."""

        url_path = media_item.db_path
        query = "UPDATE media SET completed = 1, completed_at = CURRENT_TIMESTAMP WHERE domain = ? and url_path = ?"
        await self.db_conn.execute(query, (domain, url_path))
        await self.db_conn.commit()

    async def add_filesize(self, domain: str, media_item: MediaItem) -> None:
        """Adds the file size to the db."""

        url_path = media_item.db_path
        file_size = media_item.complete_file.stat().st_size
        query = """UPDATE media SET file_size=? WHERE domain = ? and url_path = ?"""
        await self.db_conn.execute(query, (file_size, domain, url_path))
        await self.db_conn.commit()

    async def add_duration(self, domain: str, media_item: MediaItem) -> None:
        """Adds the duration to the db."""

        url_path = media_item.db_path
        query = "UPDATE media SET duration=? WHERE domain = ? and url_path = ?"
        await self.db_conn.execute(query, (media_item.duration, domain, url_path))
        await self.db_conn.commit()

    async def get_duration(self, domain: str, media_item: MediaItem) -> float | None:
        """Returns the duration from the database."""
        if media_item.is_segment:
            return

        url_path = media_item.db_path
        query = "SELECT duration FROM media WHERE domain = ? and url_path = ?"
        cursor = await self.db_conn.execute(query, (domain, url_path))
        if row := await cursor.fetchone():
            return row[0]

    async def add_download_filename(self, domain: str, media_item: MediaItem) -> None:
        """Add the download_filename to the db."""
        url_path = media_item.db_path
        query = "UPDATE media SET download_filename=? WHERE domain = ? and url_path = ? and download_filename = ''"
        await self.db_conn.execute(query, (media_item.download_filename, domain, url_path))
        await self.db_conn.commit()

    async def check_filename_exists(self, filename: str) -> bool:
        """Checks whether a downloaded filename exists in the database."""
        query = "SELECT EXISTS(SELECT 1 FROM media WHERE download_filename = ?)"
        cursor = await self.db_conn.execute(query, (filename,))
        row = await cursor.fetchone()
        # TODO: this is a bug. It should check the first index
        return row == 1

    async def get_downloaded_filename(self, domain: str, media_item: MediaItem) -> str | None:
        """Returns the downloaded filename from the database."""

        if media_item.is_segment:
            return media_item.filename

        url_path = media_item.db_path
        query = "SELECT download_filename FROM media WHERE domain = ? and url_path = ?"
        cursor = await self.db_conn.execute(query, (domain, url_path))
        if row := await cursor.fetchone():
            return row[0]

    async def get_failed_items(self) -> AsyncGenerator[list[Row]]:
        """Returns a list of failed items."""
        query = "SELECT referer, download_path,completed_at,created_at FROM media WHERE completed = 0"
        cursor = await self.db_conn.execute(query)
        while rows := await cursor.fetchmany(_FETCH_MANY_SIZE):
            yield cast("list[Row]", rows)

    async def get_all_items(self, after: datetime.date, before: datetime.date) -> AsyncGenerator[list[Row]]:
        """Returns a list of all items."""
        query = """
        SELECT referer,download_path,completed_at,created_at
        FROM media WHERE COALESCE(completed_at, '1970-01-01') BETWEEN ? AND ?
        ORDER BY completed_at DESC;
        """
        cursor = await self.db_conn.execute(query, (after.isoformat(), before.isoformat()))
        while rows := await cursor.fetchmany(_FETCH_MANY_SIZE):
            yield cast("list[Row]", rows)

    async def get_unique_download_paths(self) -> AsyncGenerator[list[Row]]:
        """Returns a list of unique download paths."""
        query = "SELECT DISTINCT download_path FROM media"
        cursor = await self.db_conn.execute(query)
        while rows := await cursor.fetchmany(_FETCH_MANY_SIZE):
            yield cast("list[Row]", rows)

    async def get_all_bunkr_failed(self) -> AsyncGenerator[list[Row]]:
        async for rows in self.get_all_bunkr_failed_via_hash():
            yield rows
        async for rows in self.get_all_bunkr_failed_via_size():
            yield rows

    async def get_all_bunkr_failed_via_size(self) -> AsyncGenerator[list[Row]]:
        query = "SELECT referer,download_path,completed_at,created_at from media WHERE file_size=322509;"
        try:
            cursor = await self.db_conn.execute(query)
            while rows := await cursor.fetchmany(_FETCH_MANY_SIZE):
                yield cast("list[Row]", rows)

        except Exception as e:
            log(f"Error getting bunkr failed via size: {e}", 40, exc_info=e)

    async def get_all_bunkr_failed_via_hash(self) -> AsyncGenerator[list[Row]]:
        query = """
        SELECT m.referer,download_path,completed_at,created_at
        FROM hash h INNER JOIN media m ON h.download_filename= m.download_filename
        WHERE h.hash = 'eb669b6362e031fa2b0f1215480c4e30';
        """

        try:
            cursor = await self.db_conn.execute(query)
            while rows := await cursor.fetchmany(_FETCH_MANY_SIZE):
                yield cast("list[Row]", rows)

        except Exception as e:
            log(f"Error getting bunkr failed via hash: {e}", 40, exc_info=e)

    async def fix_primary_keys(self) -> None:
        domain_column, *_ = await self._get_media_table_columns()
        domain_is_primary_key: bool = domain_column["pk"] != 0
        if domain_is_primary_key:
            return

        await self.db_conn.execute(create_fixed_history)
        await self.db_conn.commit()
        script = """
        INSERT INTO media_copy (domain, url_path, referer, download_path,
        download_filename, original_filename, completed)
        SELECT * FROM media GROUP BY domain, url_path, original_filename;
        DROP TABLE media;
        ALTER TABLE media_copy RENAME TO media;
        """
        await self.db_conn.executescript(script)
        await self.db_conn.commit()

    async def _get_media_table_columns(self) -> list[Row]:
        query = "pragma table_info(media)"
        cursor = await self.db_conn.execute(query)
        return cast("list[Row]", await cursor.fetchall())

    async def add_columns_media(self) -> None:
        columns = await self._get_media_table_columns()
        current_column_names: tuple[str, ...] = tuple(col["name"] for col in columns)
        new_columns = (
            ("album_id", "TEXT"),
            ("created_at", "TIMESTAMP"),
            ("completed_at", "TIMESTAMP"),
            ("file_size", "INT"),
            ("duration", "FLOAT"),
        )

        script = ""
        for name, type_ in new_columns:
            if name not in current_column_names:
                script += f"ALTER TABLE media ADD COLUMN {name} {type_};"

        if script:
            await self.db_conn.executescript(script)
            await self.db_conn.commit()
