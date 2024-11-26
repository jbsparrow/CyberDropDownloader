from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path
from typing import TYPE_CHECKING

from cyberdrop_dl.utils.utilities import sanitize_folder

if TYPE_CHECKING:
    from rich.progress import TaskID
    from yarl import URL


class ScrapeItemType(IntEnum):
    FORUM = 0
    FORUM_POST = 1
    FILE_HOST_PROFILE = 2
    FILE_HOST_ALBUM = 3


FORUM = ScrapeItemType.FORUM
FORUM_POST = ScrapeItemType.FORUM_POST
FILE_HOST_PROFILE = ScrapeItemType.FILE_HOST_PROFILE
FILE_HOST_ALBUM = ScrapeItemType.FILE_HOST_ALBUM


@dataclass(unsafe_hash=True)
class MediaItem:
    url: URL
    origin: ScrapeItem
    download_folder: Path
    filename: str
    original_filename: str | None = None
    debrid_link: URL | None = None

    file_lock_reference_name: str | None = field(default=None, init=False)
    download_filename: str | None = field(default=None, init=False)
    datetime: str | None = field(default=None, init=False)
    filesize: int | None = field(default=None, init=False)
    current_attempt: int = field(default=0, init=False)
    partial_file: Path | None = field(default=None, init=False)
    complete_file: Path | None = field(default=None, init=False)
    task_id: TaskID | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        self.referer = self.origin.url
        self.album_id = self.origin.album_id
        self.ext = Path(self.filename).suffix
        self.original_filename = self.original_filename or self.filename
        self.parents = self.origin.parents.copy()


@dataclass(kw_only=True)
class ScrapeItem:
    url: URL
    parent_title: str = ""
    part_of_album: bool = False
    album_id: str | None = None
    possible_datetime: int | None = None
    retry: bool = False
    retry_path: Path | None = None

    parents: list[URL] = field(default_factory=list, init=False)
    children: int = field(default=0, init=False)
    children_limit: int = field(default=0, init=False)
    type: int | None = field(default=None, init=False)
    completed_at: int | None = field(default=None, init=False)
    created_at: int | None = field(default=None, init=False)

    def add_to_parent_title(self, title: str) -> None:
        """Adds a title to the parent title."""
        if not title or self.retry:
            return
        title = sanitize_folder(title)
        self.parent_title = (self.parent_title + "/" + title) if self.parent_title else title
