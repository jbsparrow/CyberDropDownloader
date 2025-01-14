from __future__ import annotations

import contextlib
from dataclasses import InitVar, dataclass, field
from enum import IntEnum
from pathlib import Path
from typing import TYPE_CHECKING

from cyberdrop_dl.clients.errors import MaxChildrenError
from cyberdrop_dl.utils.utilities import sanitize_folder

if TYPE_CHECKING:
    from rich.progress import TaskID
    from yarl import URL

    from cyberdrop_dl.managers.manager import Manager


class ScrapeItemType(IntEnum):
    FORUM = 0
    FORUM_POST = 1
    FILE_HOST_PROFILE = 2
    FILE_HOST_ALBUM = 3


FORUM = ScrapeItemType.FORUM
FORUM_POST = ScrapeItemType.FORUM_POST
FILE_HOST_PROFILE = ScrapeItemType.FILE_HOST_PROFILE
FILE_HOST_ALBUM = ScrapeItemType.FILE_HOST_ALBUM


@dataclass(unsafe_hash=True, slots=True)
class MediaItem:
    url: URL
    origin: InitVar[ScrapeItem]
    download_folder: Path
    filename: str
    original_filename: str | None = None
    debrid_link: URL | None = field(default=None, hash=False, compare=False)

    # exclude from __init__
    file_lock_reference_name: str | None = field(default=None, init=False)
    download_filename: str | None = field(default=None, init=False)
    filesize: int | None = field(default=None, init=False)
    current_attempt: int = field(default=0, init=False, hash=False, compare=False)
    partial_file: Path | None = field(default=None, init=False)
    complete_file: Path | None = field(default=None, init=False)
    task_id: TaskID | None = field(default=None, init=False, hash=False, compare=False)

    # slots for __post_init__
    referer: URL = field(init=False)
    album_id: str = field(init=False)
    ext: str = field(init=False)
    datetime: int | None = field(init=False, hash=False, compare=False)
    parents: list[URL] = field(init=False, hash=False, compare=False)

    def __post_init__(self, origin: ScrapeItem) -> None:
        self.referer = origin.url
        self.album_id = origin.album_id
        self.ext = Path(self.filename).suffix
        self.original_filename = self.original_filename or self.filename
        self.parents = origin.parents.copy()
        self.datetime = origin.possible_datetime


@dataclass(kw_only=True, slots=True)
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
    children_limits: list[int] = field(default=list, init=False)

    def add_to_parent_title(self, title: str) -> None:
        """Adds a title to the parent title."""
        if not title or self.retry:
            return
        title = sanitize_folder(title)
        self.parent_title = (self.parent_title + "/" + title) if self.parent_title else title

    def set_type(self, scrape_item_type: ScrapeItemType, manager: Manager) -> None:
        self.type = scrape_item_type
        self.children_limit = manager.config_manager.settings_data.download_options.maximum_number_of_children
        self.reset_childen()

    def reset_childen(self) -> None:
        self.children = self.children_limit = 0
        with contextlib.suppress(IndexError, TypeError):
            self.children_limit = self.children_limit[self.type]

    def add_children(self, number: int = 1) -> None:
        self.children += number
        if self.children_limit and self.children >= self.children_limit:
            raise MaxChildrenError(origin=self)
