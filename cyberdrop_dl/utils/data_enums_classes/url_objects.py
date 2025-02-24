from __future__ import annotations

import contextlib
import copy
from dataclasses import InitVar, dataclass, field
from enum import IntEnum
from functools import partialmethod
from pathlib import Path
from typing import TYPE_CHECKING

from yarl import URL

from cyberdrop_dl.clients.errors import MaxChildrenError
from cyberdrop_dl.utils.utilities import sanitize_folder

if TYPE_CHECKING:
    from rich.progress import TaskID

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
    duration: float | None = field(default=None, hash=False, compare=False)
    ext: str = ""

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
    album_id: str | None = field(init=False)
    datetime: int | None = field(init=False, hash=False, compare=False)
    parents: list[URL] = field(init=False, hash=False, compare=False)
    parent_threads: set[URL] = field(init=False, hash=False, compare=False)

    def __post_init__(self, origin: ScrapeItem) -> None:
        self.referer = origin.url
        self.album_id = origin.album_id
        self.ext = self.ext or Path(self.filename).suffix
        self.original_filename = self.original_filename or self.filename
        self.parents = origin.parents.copy()
        self.datetime = origin.possible_datetime
        self.parent_threads = origin.parent_threads.copy()


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
    parent_threads: set[URL] = field(default_factory=set, init=False)
    children: int = field(default=0, init=False)
    children_limit: int = field(default=0, init=False)
    type: ScrapeItemType | None = field(default=None, init=False)
    completed_at: int | None = field(default=None, init=False)
    created_at: int | None = field(default=None, init=False)
    children_limits: list[int] = field(default_factory=list, init=False)

    def add_to_parent_title(self, title: str) -> None:
        """Adds a title to the parent title."""
        if not title or self.retry:
            return
        title = sanitize_folder(title)
        self.parent_title = (self.parent_title + "/" + title) if self.parent_title else title

    def set_type(self, scrape_item_type: ScrapeItemType | None, _: Manager | None = None) -> None:
        self.type = scrape_item_type
        self.reset_childen()

    def reset_childen(self) -> None:
        self.children = self.children_limit = 0
        if self.type is None:
            return
        with contextlib.suppress(IndexError, TypeError):
            self.children_limit = self.children_limits[self.type]

    def add_children(self, number: int = 1) -> None:
        self.children += number
        if self.children_limit and self.children >= self.children_limit:
            raise MaxChildrenError(origin=self)

    def reset(self, reset_parents: bool = False, reset_parent_title: bool = False) -> None:
        """Resets `album_id`, `type` and `posible_datetime` back to `None`

        Only useful when the scrape item will be send to a different crawler and you want to get a diferent download path
        """
        self.album_id = self.possible_datetime = self.type = None
        self.reset_childen()
        if reset_parents:
            self.parents = []
            self.parent_threads = set()
        if reset_parent_title:
            self.parent_title = ""

    def setup_as(self, title: str, type: ScrapeItemType) -> None:
        self.part_of_album = True
        self.set_type(type)
        self.add_to_parent_title(title)

    def create_new(
        self,
        url: URL,
        *,
        new_title_part: str = "",
        part_of_album: bool = False,
        album_id: str | None = None,
        possible_datetime: int | None = None,
        add_parent: URL | bool | None = None,
    ) -> ScrapeItem:
        """Creates a scrape item."""
        scrape_item = copy.deepcopy(self)
        scrape_item.url = url
        if add_parent:
            new_parent = add_parent if isinstance(add_parent, URL) else self.url
            scrape_item.parents.append(new_parent)
        if new_title_part:
            scrape_item.add_to_parent_title(new_title_part)
        scrape_item.part_of_album = part_of_album or scrape_item.part_of_album
        scrape_item.possible_datetime = possible_datetime or scrape_item.possible_datetime
        scrape_item.album_id = album_id or scrape_item.album_id
        return scrape_item

    create_child = partialmethod(create_new, part_of_album=True, add_parent=True)
    setup_as_album = partialmethod(setup_as, type=FILE_HOST_ALBUM)
    setup_as_profile = partialmethod(setup_as, type=FILE_HOST_PROFILE)
    setup_as_forum = partialmethod(setup_as, type=FORUM)
    setup_as_post = partialmethod(setup_as, type=FORUM_POST)

    def origin(self) -> URL | None:
        if self.parents:
            return self.parents[0]

    def parent(self) -> URL | None:
        if self.parents:
            return self.parents[-1]
