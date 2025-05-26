from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import datetime
    from collections.abc import AsyncGenerator, Generator, Iterable
    from pathlib import Path

    import aiosqlite

    from cyberdrop_dl.data_structures.url_objects import MediaItem
    from cyberdrop_dl.types import AbsoluteHttpURL, Hash, HashAlgorithm


class DBTable(ABC):
    db: Database

    @abstractmethod
    async def create(self) -> None: ...


class HashTable(DBTable):
    @abstractmethod
    async def get_file_hash_if_exists(self, file: Path, hash_type: HashAlgorithm) -> Hash | None: ...

    @abstractmethod
    async def get_files_with_hash_matches(self, hash: Hash, size: int) -> AsyncGenerator[Path]: ...

    @abstractmethod
    async def insert_or_update_hash_db(
        self, file: Path, original_filename: str | None, referer: AbsoluteHttpURL | None, hash: Hash
    ) -> bool: ...


class HistoryTable(DBTable):
    @abstractmethod
    async def check_complete(self, domain: str, url: AbsoluteHttpURL, referer: AbsoluteHttpURL) -> bool: ...

    @abstractmethod
    async def check_album(self, domain: str, album_id: str) -> dict[str, int]: ...

    @abstractmethod
    async def set_album_id(self, domain: str, media_item: MediaItem) -> None: ...

    @abstractmethod
    async def check_complete_by_referer(self, domain: str, referer: AbsoluteHttpURL) -> bool: ...

    @abstractmethod
    async def insert_incompleted(self, domain: str, media_item: MediaItem) -> None: ...

    @abstractmethod
    async def mark_complete(self, domain: str, media_item: MediaItem) -> None: ...

    @abstractmethod
    async def add_filesize(self, domain: str, media_item: MediaItem) -> None: ...

    @abstractmethod
    async def add_duration(self, domain: str, media_item: MediaItem) -> None: ...

    @abstractmethod
    async def get_duration(self, domain: str, media_item: MediaItem) -> float | None: ...

    @abstractmethod
    async def add_download_filename(self, domain: str, media_item: MediaItem) -> None: ...

    @abstractmethod
    async def check_filename_exists(self, filename: str) -> bool: ...

    @abstractmethod
    async def get_downloaded_filename(self, domain: str, media_item: MediaItem) -> str | None: ...

    @abstractmethod
    async def get_failed_items(self) -> Iterable[aiosqlite.Row]: ...

    @abstractmethod
    async def get_all_items(self, after: datetime.date, before: datetime.date) -> Iterable[aiosqlite.Row]: ...

    @abstractmethod
    async def get_all_bunkr_failed(self) -> list[tuple[str, str, str, str]]: ...


class TempRefererTable(DBTable):
    @abstractmethod
    async def check_referer(self, referer: AbsoluteHttpURL) -> bool: ...


class Database(ABC):
    hash_table: HashTable
    history_table: HistoryTable
    temp_referer_table: TempRefererTable

    @abstractmethod
    async def connect() -> None: ...
    @abstractmethod
    async def close(self) -> None: ...

    def get_tables(self) -> Generator[DBTable]:
        yield self.hash_table
        yield self.history_table
        yield self.temp_referer_table
