from __future__ import annotations

from dataclasses import field
from pathlib import Path
from typing import TYPE_CHECKING

from cyberdrop_dl.utils.utilities import sanitize_folder

if TYPE_CHECKING:
    from rich.progress import TaskID
    from yarl import URL


FORUM = 0
FORUM_POST = 1
FILE_HOST_PROFILE = 2
FILE_HOST_ALBUM = 3
SCRAPE_ITEM_TYPES = [FORUM, FORUM_POST, FILE_HOST_PROFILE, FILE_HOST_ALBUM]


class MediaItem:
    def __init__(
        self,
        url: URL,
        origin: ScrapeItem,
        download_folder: Path,
        filename: Path | str,
        original_filename: Path | str | None = None,
        debrid_link: URL | None = None,
    ) -> None:
        self.url: URL = url
        self.referer: URL = origin.url
        self.debrid_link: URL | None = debrid_link
        self.album_id: str | None = origin.album_id
        self.download_folder: Path = download_folder
        self.filename: str = str(filename)
        self.ext: str = Path(filename).suffix
        self.download_filename: str = field(init=False)
        self.original_filename: str = str(original_filename) if original_filename else self.filename
        self.file_lock_reference_name: str = field(init=False)
        self.datetime: str = field(init=False)
        self.parents = origin.parents.copy()

        self.filesize: int = field(init=False)
        self.current_attempt: int = field(init=False)

        self.partial_file: Path | None = field(init=False)
        self.complete_file: Path = field(init=False)
        self.task_id: TaskID = field(init=False)


class ScrapeItem:
    def __init__(
        self,
        url: URL,
        parent_title: str,
        part_of_album: bool = False,
        album_id: str | None = None,
        possible_datetime: int | None = None,
        retry: bool = False,
        retry_path: Path | None = None,
    ) -> None:
        self.url: URL = url
        self.parent_title: str = parent_title
        # WARNING: unsafe but deepcopy is used when a new child item is created
        self.parents: list[URL] = []
        self.children: int = 0
        self.children_limit: int = 0
        self.type: int | None = None
        self.part_of_album: bool = part_of_album
        self.album_id: str | None = album_id
        self.possible_datetime: int = possible_datetime
        self.retry: bool = retry
        self.retry_path: Path = retry_path
        self.completed_at = None
        self.created_at = None

    def add_to_parent_title(self, title: str) -> None:
        """Adds a title to the parent title."""
        if not title or self.retry:
            return
        title = sanitize_folder(title)
        self.parent_title = (self.parent_title + "/" + title) if self.parent_title else title
