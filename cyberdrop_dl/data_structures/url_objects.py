# type: ignore[reportIncompatibleVariableOverride]
from __future__ import annotations

import copy
import datetime
from dataclasses import asdict, dataclass, field
from enum import IntEnum
from functools import partialmethod
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, NamedTuple, ParamSpec, Self, TypeVar, overload

import yarl

from cyberdrop_dl.exceptions import MaxChildrenError

P = ParamSpec("P")
R = TypeVar("R")
T = TypeVar("T")

if TYPE_CHECKING:
    import functools
    import inspect
    from collections.abc import Callable

    import aiohttp
    from propcache.api import under_cached_property as cached_property
    from rich.progress import TaskID

    from cyberdrop_dl.managers.manager import Manager

    def copy_signature(target: Callable[P, R]) -> Callable[[Callable[..., T]], Callable[P, T]]:
        def decorator(func: Callable[..., T]) -> Callable[P, T]:
            @functools.wraps(func)
            def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
                return func(*args, **kwargs)

            wrapper.__signature__ = inspect.signature(target).replace(  # type: ignore
                return_annotation=inspect.signature(func).return_annotation
            )
            return wrapper

        return decorator

    class AbsoluteHttpURL(yarl.URL):
        @copy_signature(yarl.URL.__new__)
        def __new__(cls) -> AbsoluteHttpURL: ...

        @copy_signature(yarl.URL.__truediv__)
        def __truediv__(self) -> AbsoluteHttpURL: ...

        @copy_signature(yarl.URL.__mod__)
        def __mod__(self) -> AbsoluteHttpURL: ...

        @cached_property
        def host(self) -> str: ...

        @cached_property
        def scheme(self) -> Literal["http", "https"]: ...

        @cached_property
        def absolute(self) -> Literal[True]: ...

        @cached_property
        def parent(self) -> AbsoluteHttpURL: ...

        @copy_signature(yarl.URL.with_path)
        def with_path(self) -> AbsoluteHttpURL: ...

        @copy_signature(yarl.URL.with_host)
        def with_host(self) -> AbsoluteHttpURL: ...

        @copy_signature(yarl.URL.origin)
        def origin(self) -> AbsoluteHttpURL: ...

        @overload
        def with_query(self, query: yarl.Query) -> AbsoluteHttpURL: ...

        @overload
        def with_query(self, **kwargs: yarl.QueryVariable) -> AbsoluteHttpURL: ...

        @copy_signature(yarl.URL.with_query)
        def with_query(self) -> AbsoluteHttpURL: ...

        @overload
        def extend_query(self, query: yarl.Query) -> AbsoluteHttpURL: ...

        @overload
        def extend_query(self, **kwargs: yarl.QueryVariable) -> AbsoluteHttpURL: ...

        @copy_signature(yarl.URL.extend_query)
        def extend_query(self) -> AbsoluteHttpURL: ...

        @overload
        def update_query(self, query: yarl.Query) -> AbsoluteHttpURL: ...

        @overload
        def update_query(self, **kwargs: yarl.QueryVariable) -> AbsoluteHttpURL: ...

        @copy_signature(yarl.URL.update_query)
        def update_query(self) -> AbsoluteHttpURL: ...

        @copy_signature(yarl.URL.without_query_params)
        def without_query_params(self) -> AbsoluteHttpURL: ...

        @copy_signature(yarl.URL.with_fragment)
        def with_fragment(self) -> AbsoluteHttpURL: ...

        @copy_signature(yarl.URL.with_name)
        def with_name(self) -> AbsoluteHttpURL: ...

        @copy_signature(yarl.URL.with_suffix)
        def with_suffix(self) -> AbsoluteHttpURL: ...

        @copy_signature(yarl.URL.join)
        def join(self) -> AbsoluteHttpURL: ...

        @copy_signature(yarl.URL.joinpath)
        def joinpath(self) -> AbsoluteHttpURL: ...

else:
    AbsoluteHttpURL = yarl.URL

    def copy_signature(_):
        def call(y):
            return y

        return call


AnyURL = TypeVar("AnyURL", bound=yarl.URL | AbsoluteHttpURL)


class ScrapeItemType(IntEnum):
    FORUM = 0
    FORUM_POST = 1
    FILE_HOST_PROFILE = 2
    FILE_HOST_ALBUM = 3


FORUM = ScrapeItemType.FORUM
FORUM_POST = ScrapeItemType.FORUM_POST
FILE_HOST_PROFILE = ScrapeItemType.FILE_HOST_PROFILE
FILE_HOST_ALBUM = ScrapeItemType.FILE_HOST_ALBUM


class HlsSegment(NamedTuple):
    part: str
    name: str
    url: AbsoluteHttpURL


@dataclass(unsafe_hash=True, slots=True, kw_only=True)
class MediaItem:
    url: AbsoluteHttpURL
    domain: str
    referer: AbsoluteHttpURL
    download_folder: Path
    filename: str
    original_filename: str
    download_filename: str | None = field(default=None)
    filesize: int | None = field(default=None, compare=False)
    ext: str
    debrid_link: AbsoluteHttpURL | None = field(default=None, compare=False)
    duration: float | None = field(default=None, compare=False)
    is_segment: bool = False
    fallbacks: Callable[[aiohttp.ClientResponse, int], AbsoluteHttpURL] | list[AbsoluteHttpURL] | None = field(
        default=None, compare=False
    )
    album_id: str | None = None
    datetime: int | None = field(default=None, compare=False)
    parents: list[AbsoluteHttpURL] = field(default_factory=list, compare=False)
    parent_threads: set[AbsoluteHttpURL] = field(default_factory=set, compare=False)

    current_attempt: int = field(default=0, compare=False)
    partial_file: Path = None  # type: ignore
    complete_file: Path = None  # type: ignore
    hash: str | None = field(default=None, compare=False)
    downloaded: bool = field(default=False, compare=False)

    parent_media_item: MediaItem | None = field(default=None, compare=False)
    db_path: str = field(init=False, repr=False)
    _task_id: TaskID | None = field(default=None, compare=False)

    def __post_init__(self) -> None:
        self.db_path = self.create_db_path(self.url, self.domain)

    @staticmethod
    def create_db_path(url: yarl.URL, domain: str) -> str:
        """Gets the URL path to be put into the DB and checked from the DB."""

        if domain:
            if "e-hentai" in domain:
                return url.path.split("keystamp")[0][:-1]

            if "mediafire" in domain:
                return url.name

            if "mega.nz" in domain:
                return url.path_qs if not (frag := url.fragment) else f"{url.path_qs}#{frag}"

        return url.path

    @staticmethod
    def from_item(
        origin: ScrapeItem | MediaItem,
        url: AbsoluteHttpURL,
        /,
        domain: str,
        download_folder: Path,
        filename: str,
        original_filename: str | None = None,
        debrid_link: AbsoluteHttpURL | None = None,
        duration: float | None = None,
        ext: str = "",
        is_segment: bool = False,
        fallbacks: Callable[[aiohttp.ClientResponse, int], AbsoluteHttpURL] | list[AbsoluteHttpURL] | None = None,
    ) -> MediaItem:
        return MediaItem(
            url=url,
            domain=domain,
            download_folder=download_folder,
            filename=filename,
            debrid_link=debrid_link,
            duration=duration,
            referer=origin.url,
            album_id=origin.album_id,
            ext=ext or Path(filename).suffix,
            original_filename=original_filename or filename,
            is_segment=is_segment,
            fallbacks=fallbacks,
            parents=origin.parents.copy(),
            datetime=origin.possible_datetime if isinstance(origin, ScrapeItem) else origin.datetime,
            parent_media_item=None if isinstance(origin, ScrapeItem) else origin,
            parent_threads=origin.parent_threads.copy(),
        )

    @property
    def task_id(self) -> TaskID | None:
        if self.parent_media_item is not None:
            return self.parent_media_item.task_id
        return self._task_id

    def set_task_id(self, task_id: TaskID | None) -> None:
        if self.task_id is not None and task_id is not None:
            # We already have a task_id; we can't replace it, only reset it.
            # This should never happen. Calling code should always check the value before making a new task.
            # We can't silently ignore it either because we will lose any reference to the created task.
            raise ValueError("task_id is already set")
        if self.parent_media_item is not None:
            self.parent_media_item.set_task_id(task_id)
        else:
            self._task_id = task_id

    def as_jsonable_dict(self) -> dict[str, Any]:
        item = asdict(self)
        if self.datetime:
            assert isinstance(self.datetime, int), f"Invalid {self.datetime =!r} from {self.referer}"
            item["datetime"] = datetime.datetime.fromtimestamp(self.datetime)
        item["attempts"] = item.pop("current_attempt")
        if self.hash:
            item["hash"] = f"xxh128:{self.hash}"
        for name in ("fallbacks", "_task_id", "is_segment", "parent_media_item"):
            _ = item.pop(name)
        return item


@dataclass(kw_only=True, slots=True)
class ScrapeItem:
    url: AbsoluteHttpURL
    parent_title: str = ""
    part_of_album: bool = False
    album_id: str | None = None
    possible_datetime: int | None = None
    retry: bool = False
    retry_path: Path | None = None

    parents: list[AbsoluteHttpURL] = field(default_factory=list, init=False)
    parent_threads: set[AbsoluteHttpURL] = field(default_factory=set, init=False)
    children: int = field(default=0, init=False)
    children_limit: int = field(default=0, init=False)
    type: ScrapeItemType | None = field(default=None, init=False)
    completed_at: int | None = field(default=None, init=False)
    created_at: int | None = field(default=None, init=False)
    children_limits: list[int] = field(default_factory=list, init=False)

    def add_to_parent_title(self, title: str) -> None:
        """Adds a title to the parent title."""
        from cyberdrop_dl.utils.utilities import sanitize_folder

        if not title or self.retry:
            return
        title = sanitize_folder(title)
        if title.endswith(")") and " (" in title:
            for part in reversed(self.parent_title.split("/")):
                if part.endswith(")") and " (" in part:
                    last_domain_suffix = part.rpartition(" (")[-1]
                    break
            else:
                last_domain_suffix = None

            if last_domain_suffix:
                og_title, _, domain_suffix = title.rpartition(" (")
                if last_domain_suffix == domain_suffix:
                    title = og_title

        self.parent_title = (self.parent_title + "/" + title) if self.parent_title else title

    def set_type(self, scrape_item_type: ScrapeItemType | None, _: Manager | None = None) -> None:
        self.type = scrape_item_type
        self.reset_childen()

    def reset_childen(self) -> None:
        self.children = self.children_limit = 0
        if self.type is None:
            return
        try:
            self.children_limit = self.children_limits[self.type]
        except (IndexError, TypeError):
            pass

    def add_children(self, number: int = 1) -> None:
        self.children += number
        if self.children_limit and self.children >= self.children_limit:
            raise MaxChildrenError(origin=self)

    def reset(self, reset_parents: bool = False, reset_parent_title: bool = False) -> None:
        """Resets `album_id`, `type` and `posible_datetime` back to `None`

        Reset `part_of_album` back to `False`
        """
        self.album_id = self.possible_datetime = self.type = None
        self.part_of_album = False
        self.reset_childen()
        if reset_parents:
            self.parents = []
            self.parent_threads = set()
        if reset_parent_title:
            self.parent_title = ""

    def setup_as(self, title: str, type: ScrapeItemType, *, album_id: str | None = None) -> None:
        self.part_of_album = True
        if album_id:
            self.album_id = album_id
        if self.type != type:
            self.set_type(type)
        self.add_to_parent_title(title)

    def create_new(
        self,
        url: AbsoluteHttpURL,
        *,
        new_title_part: str = "",
        part_of_album: bool = False,
        album_id: str | None = None,
        possible_datetime: int | None = None,
        add_parent: AbsoluteHttpURL | bool | None = None,
    ) -> ScrapeItem:
        """Creates a scrape item."""
        from cyberdrop_dl.utils.utilities import is_absolute_http_url

        scrape_item = self.copy()
        assert is_absolute_http_url(url)
        scrape_item.url = url
        if add_parent:
            new_parent = add_parent if isinstance(add_parent, AbsoluteHttpURL) else self.url
            assert is_absolute_http_url(new_parent)
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

    @property
    def origin(self) -> AbsoluteHttpURL | None:
        if self.parents:
            return self.parents[0]

    @property
    def parent(self) -> AbsoluteHttpURL | None:
        if self.parents:
            return self.parents[-1]

    def copy(self) -> Self:
        """Returns a deep copy of this scrape_item"""
        return copy.deepcopy(self)

    def pop_query(self, name: str) -> str | None:
        """Get the value of a query param and remove it from this item's URL"""
        value = self.url.query.get(name)
        self.url = self.url.without_query_params(name)
        return value


class QueryDatetimeRange(NamedTuple):
    before: datetime.datetime | None = None
    after: datetime.datetime | None = None

    @staticmethod
    def from_url(url: AbsoluteHttpURL) -> QueryDatetimeRange | None:
        self = QueryDatetimeRange(_date_from_query_param(url, "before"), _date_from_query_param(url, "after"))
        if self == (None, None):
            return None
        if (self.before and self.after) and (self.before <= self.after):
            raise ValueError
        return self

    def is_in_range(self, other: datetime.datetime) -> bool:
        if (self.before and other >= self.before) or (self.after and other <= self.after):
            return False
        return True

    def as_query(self) -> dict[str, Any]:
        return {name: value.isoformat() for name, value in self._asdict().items() if value}


def _date_from_query_param(url: AbsoluteHttpURL, query_param: str) -> datetime.datetime | None:
    from cyberdrop_dl.utils.dates import parse_aware_iso_datetime

    if value := url.query.get(query_param):
        return parse_aware_iso_datetime(value)
