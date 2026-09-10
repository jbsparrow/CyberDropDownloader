from __future__ import annotations

import base64
import contextlib
import copy
import dataclasses
import datetime
import logging
from enum import IntEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Self, final, overload

import yarl
from typing_extensions import TypeIs

from cyberdrop_dl import signature
from cyberdrop_dl.exceptions import MaxChildrenError
from cyberdrop_dl.filepath import sanitize_folder

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Generator, Iterable, Mapping, Sequence

    @final
    class AbsoluteHttpURL(yarl.URL):
        @signature.copy(yarl.URL.__new__)
        def __new__(cls) -> Self: ...

        @signature.copy(yarl.URL.__truediv__)
        def __truediv__(self, name: str) -> AbsoluteHttpURL: ...

        @signature.copy(yarl.URL.__mod__)
        def __mod__(self, query: object) -> AbsoluteHttpURL: ...

        @property
        def host(self) -> str: ...  # pyright: ignore[reportIncompatibleVariableOverride]

        @property
        def scheme(self) -> Literal["http", "https"]: ...  # pyright: ignore[reportIncompatibleVariableOverride]

        @property
        def absolute(self) -> Literal[True]: ...  # pyright: ignore[reportIncompatibleVariableOverride]

        @property
        def parent(self) -> AbsoluteHttpURL: ...  # pyright: ignore[reportIncompatibleVariableOverride]

        @signature.copy(yarl.URL.with_path)
        def with_path(self) -> AbsoluteHttpURL: ...

        @signature.copy(yarl.URL.with_host)
        def with_host(self) -> AbsoluteHttpURL: ...

        @signature.copy(yarl.URL.origin)
        def origin(self) -> AbsoluteHttpURL: ...

        @overload
        def with_query(self, query: yarl.Query) -> AbsoluteHttpURL: ...

        @overload
        def with_query(self, **kwargs: yarl.QueryVariable) -> AbsoluteHttpURL: ...

        @signature.copy(yarl.URL.with_query)
        def with_query(self) -> AbsoluteHttpURL: ...

        @overload
        def extend_query(self, query: yarl.Query) -> AbsoluteHttpURL: ...

        @overload
        def extend_query(self, **kwargs: yarl.QueryVariable) -> AbsoluteHttpURL: ...

        @signature.copy(yarl.URL.extend_query)
        def extend_query(self) -> AbsoluteHttpURL: ...

        @overload
        def update_query(self, query: yarl.Query) -> AbsoluteHttpURL: ...

        @overload
        def update_query(self, **kwargs: yarl.QueryVariable) -> AbsoluteHttpURL: ...

        @signature.copy(yarl.URL.update_query)
        def update_query(self) -> AbsoluteHttpURL: ...

        @signature.copy(yarl.URL.without_query_params)
        def without_query_params(self) -> AbsoluteHttpURL: ...

        @signature.copy(yarl.URL.with_fragment)
        def with_fragment(self) -> AbsoluteHttpURL: ...

        @signature.copy(yarl.URL.with_name)
        def with_name(self) -> AbsoluteHttpURL: ...

        @signature.copy(yarl.URL.with_suffix)
        def with_suffix(self) -> AbsoluteHttpURL: ...

        @signature.copy(yarl.URL.join)
        def join(self) -> AbsoluteHttpURL: ...

        @signature.copy(yarl.URL.joinpath)
        def joinpath(self) -> AbsoluteHttpURL: ...

    class _FakePath(Path): ...

else:
    AbsoluteHttpURL = yarl.URL

    def _FakePath():  # noqa: N802
        return None


def is_absolute_http_url(url: yarl.URL) -> TypeIs[AbsoluteHttpURL]:
    return url.absolute and url.scheme in {"http", "https"}


class ScrapeItemType(IntEnum):
    FORUM = 0
    FORUM_POST = 1
    PROFILE = 2
    ALBUM = 3


logger = logging.getLogger(__name__)


@dataclasses.dataclass(slots=True, frozen=True)
class MuxVideo:
    video: AbsoluteHttpURL
    audio: AbsoluteHttpURL

    def __json__(self) -> dict[str, Any]:
        return {"video": str(self.video), "audio": str(self.audio)}


@final
@dataclasses.dataclass(slots=True, kw_only=True)
class MediaItem:
    url: AbsoluteHttpURL
    domain: str
    referer: AbsoluteHttpURL
    download_folder: Path
    db_path: str
    filename: str

    original_filename: str = ""
    download_filename: str | None = None
    ext: str = ""
    size: int | None = None
    debrid_url: Callable[[], Awaitable[AbsoluteHttpURL]] | AbsoluteHttpURL | None = None
    duration: float | None = None
    is_segment: bool = False
    album_id: str | None = None
    uploaded_at: int | None = None
    xxhash: str | None = None
    thumbnail: AbsoluteHttpURL | None = None

    parents: tuple[AbsoluteHttpURL, ...] = dataclasses.field(default_factory=tuple)
    attempts: int = dataclasses.field(init=False, default=0)
    partial_file: Path = dataclasses.field(init=False, default=_FakePath())
    path: Path = dataclasses.field(init=False, default=_FakePath())
    downloaded: bool = dataclasses.field(init=False, default=False)

    metadata: object = dataclasses.field(init=False, default_factory=dict)

    uploaded_at_date: datetime.datetime | None = dataclasses.field(init=False, default=None)
    extra_info: dict[str, Any] = dataclasses.field(init=False, default_factory=dict)

    id: tuple[str, ...] = dataclasses.field(init=False)
    base64_id: str = dataclasses.field(init=False)
    headers: dict[str, str] = dataclasses.field(init=False, default_factory=dict)
    json_check: Callable[..., None] | None = None

    def __post_init__(self) -> None:
        self.ext = self.ext or Path(self.filename).suffix
        self.id = self.domain, self.db_path
        self.original_filename = self.original_filename or self.filename
        if self.url.scheme == "metadata":
            self.db_path = ""
            self.id = *self.id, "metadata"

        if self.uploaded_at:
            assert type(self.uploaded_at) is int, f"Invalid {self.uploaded_at =!r} from {self.referer}"
            self.uploaded_at_date = datetime.datetime.fromtimestamp(self.uploaded_at, tz=datetime.UTC)

        self.base64_id = base64.urlsafe_b64encode("".join(self.id).encode()).decode().rstrip("=")

    __repr__ = signature.simple_repr("url", "id", "debrid_url", "uploaded_at_date")

    def __hash__(self) -> int:
        return hash(self.id)

    @property
    def real_url(self) -> AbsoluteHttpURL:
        if self.debrid_url and not callable(self.debrid_url):
            return self.debrid_url
        return self.url

    async def resolve(self) -> AbsoluteHttpURL:
        if callable(self.debrid_url):
            self.debrid_url = await self.debrid_url()

        return self.debrid_url or self.url

    def __iter__(self) -> Generator[tuple[str, Any]]:
        for field in dataclasses.fields(self):
            if field.name in ("is_segment", "json_check"):
                continue
            yield field.name, getattr(self, field.name)

    def serialize(self) -> dict[str, Any]:
        me = dict(self)
        if callable(self.debrid_url):
            me["debrid_url"] = None
        if self.xxhash:
            me["xxhash"] = f"xxh128:{self.xxhash}"
        return me

    def as_segment(self, filename: str, url: AbsoluteHttpURL) -> MediaItem:
        me = MediaItem(
            url=url,
            domain=self.domain,
            download_folder=self.download_folder,
            filename=filename,
            db_path=self.db_path,
            referer=self.url,
            album_id=self.album_id,
            ext=self.ext,
            parents=self.parents,
            uploaded_at=self.uploaded_at,
            is_segment=True,
        )
        me.headers = self.headers.copy()
        me.extra_info = self.extra_info.copy()
        return me


@dataclasses.dataclass(slots=True, frozen=True)
class RetryInfo:
    domain: str
    url_path: str
    download_path: Path
    download_filename: str
    referer: AbsoluteHttpURL


@final
@dataclasses.dataclass(kw_only=True, slots=True)
class ScrapeItem:
    url: AbsoluteHttpURL
    part_of_album: bool = False
    album_id: str | None = None
    download_folder: Path = Path("downloads")

    folders: list[str] = dataclasses.field(default_factory=list)
    parents: list[AbsoluteHttpURL] = dataclasses.field(default_factory=list)
    parent_threads: set[AbsoluteHttpURL] = dataclasses.field(default_factory=set)
    max_children: Mapping[ScrapeItemType, int] | None = None
    password: str | None = None
    referer: AbsoluteHttpURL | None = None

    _children_count: int = 0
    _children_limit: int = 0
    _type: ScrapeItemType | None = None
    _uploaded_at: int | None = None
    retry_info: RetryInfo | None = None
    markers: list[Any] = dataclasses.field(default_factory=list)

    __repr__ = signature.simple_repr("url", "folders", "uploaded_at")

    @classmethod
    def from_url(cls, url: yarl.URL | str) -> Self:
        url = AbsoluteHttpURL(url)
        assert is_absolute_http_url(url)
        get = url.query.get
        try:
            referer = _url_from_query(get("referer"))
        except ValueError:
            logger.exception(
                "Unable to parse query 'referer' value (%s) from url %s , ignoring...", get("referer"), url
            )
            referer = None

        return cls(url=url, password=get("password"), referer=referer)

    @property
    def uploaded_at(self) -> int | None:
        return self._uploaded_at

    @uploaded_at.setter
    def uploaded_at(self, value: float | None) -> None:  # pyright: ignore[reportPropertyTypeMismatch]
        self._uploaded_at = None if value is None else int(value)

    @property
    def upload_date(self) -> datetime.datetime | None:
        if self._uploaded_at:
            return datetime.datetime.fromtimestamp(self._uploaded_at, tz=datetime.UTC)

    @upload_date.setter
    def upload_date(self, date: datetime.datetime | None) -> None:
        if date:
            self.uploaded_at = date.timestamp()

    @property
    def type(self) -> ScrapeItemType | None:
        return self._type

    @type.setter  # noqa: A003
    def type(self, item_type: ScrapeItemType | None) -> None:
        self._type = item_type
        self._children_count = self._children_limit = 0
        if item_type is None or not self.max_children:
            return

        try:
            self._children_limit = self.max_children[item_type]
        except LookupError:
            pass

    @property
    @contextlib.contextmanager
    def track_changes(self) -> Generator[Self]:
        old_url = self.url
        try:
            yield self
        finally:
            if old_url != self.url:
                logger.info(f"URL transformation applied: \n  {old_url = !s}\n  new_url = {self.url}")

    def append_folders(self, *folders: str) -> None:
        for folder in folders:
            self._append_folder(folder)

    def _append_folder(self, folder: str, /) -> None:
        if not folder:
            return

        folder = sanitize_folder(folder)
        if _has_domain(folder) and (last_domain := _extract_last_domain(self.folders)):
            folder = _remove_domain_if_duplicate(folder, last_domain)

        self.folders.append(folder)

    def add_children(self, number: int = 1) -> None:
        self._children_count += number
        if self._children_limit and self._children_count >= self._children_limit:
            raise MaxChildrenError(origin=self)

    def reset(self, *, reset_parents: bool = False, reset_parent_title: bool = False) -> None:
        """Resets `album_id`, `type` and `posible_datetime` back to `None`

        Reset `part_of_album` back to `False`
        """
        self.album_id = self.uploaded_at = None
        self.type = None
        self.part_of_album = False
        if reset_parents:
            self.parents = []
            self.parent_threads = set()
        if reset_parent_title:
            self.folders.clear()

    def setup_as(self, title: str, item_type: ScrapeItemType, /, *, album_id: str | None = None) -> None:
        self.part_of_album = True
        if album_id:
            self.album_id = album_id
        if self.type != item_type:
            self.type = item_type
        self.append_folders(title)

    def create_new(
        self,
        url: AbsoluteHttpURL,
        *,
        part_of_album: bool = False,
        album_id: str | None = None,
        add_parent: AbsoluteHttpURL | bool | None = None,
    ) -> Self:
        """Creates a scrape item."""

        scrape_item = self.copy()
        assert is_absolute_http_url(url)

        if add_parent:
            new_parent = self.url if add_parent is True else add_parent
            assert is_absolute_http_url(new_parent)
            scrape_item.parents.append(new_parent)

        scrape_item.url = url
        scrape_item.part_of_album = part_of_album or scrape_item.part_of_album
        scrape_item.album_id = album_id or scrape_item.album_id
        return scrape_item

    def create_child(self, url: AbsoluteHttpURL) -> Self:
        return self.create_new(url, part_of_album=True, add_parent=True)

    def setup_as_album(self: ScrapeItem, title: str, *, album_id: str | None = None) -> None:
        return self.setup_as(title, ScrapeItemType.ALBUM, album_id=album_id)

    def setup_as_profile(self: ScrapeItem, title: str, *, album_id: str | None = None) -> None:
        return self.setup_as(title, ScrapeItemType.PROFILE, album_id=album_id)

    def setup_as_forum(self: ScrapeItem, title: str, *, album_id: str | None = None) -> None:
        return self.setup_as(title, ScrapeItemType.FORUM, album_id=album_id)

    def setup_as_post(self: ScrapeItem, title: str, *, album_id: str | None = None) -> None:
        return self.setup_as(title, ScrapeItemType.FORUM_POST, album_id=album_id)

    def create_children(self, urls: Iterable[AbsoluteHttpURL]) -> Generator[Self]:
        for url in urls:
            yield self.create_child(url)
            self.add_children()

    @property
    def is_loose_file(self) -> bool:
        return not self.folders or not self.part_of_album

    @property
    def path(self) -> Path:
        return Path(*self.folders)

    def copy(self) -> Self:
        """Returns a deep copy of this scrape_item"""
        me = copy.deepcopy(self)
        me.markers = self.markers.copy()
        return me

    def get_referer(self) -> AbsoluteHttpURL | None:
        if self.referer:
            return self.referer
        if self.parents:
            return self.parents[-1]


def _has_domain(folder: str) -> bool:
    return folder.endswith(")") and " (" in folder


def _remove_domain_if_duplicate(folder: str, last_domain: str) -> str:
    og_folder, _, current_domain = folder.rpartition(" (")
    if last_domain == current_domain[:-1]:
        return og_folder
    return folder


def _extract_last_domain(folders: Sequence[str]) -> str | None:
    for folder in reversed(folders):
        if folder.endswith(")"):
            try:
                return folder[folder.rindex("(") + 1 : -1]
            except IndexError:
                pass

    return None


def _url_from_query(query_url: str | None) -> AbsoluteHttpURL | None:
    if query_url:
        url = AbsoluteHttpURL(query_url)
        if not is_absolute_http_url(url):
            raise ValueError("URL needs to be a valid HTTP URL")
        return url
