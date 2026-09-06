from __future__ import annotations

import asyncio
import contextlib
import functools
import logging
import re
from abc import ABC, abstractmethod
from collections import Counter
from contextvars import ContextVar
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, ClassVar, Concatenate, Final, Literal, Self, final

from aiohttp import hdrs

from cyberdrop_dl import aio, env
from cyberdrop_dl.cache import TTLCacheAdapter
from cyberdrop_dl.clients.downloads import IGNORE_CONTENT_TYPE
from cyberdrop_dl.clients.http import HTTPClient, HTTPConfig, HTTPContext, HTTPMixin
from cyberdrop_dl.constants import FileExt
from cyberdrop_dl.crawlers import ALLOW_NO_EXT, SKIP_DOWNLOAD, Registry
from cyberdrop_dl.crawlers._hls import HLSMixin
from cyberdrop_dl.downloader.http import Downloader
from cyberdrop_dl.exceptions import MaxChildrenError, NoExtensionError, ScrapeError
from cyberdrop_dl.filepath import check_dangerous_filename, check_path_traversal, compose_filename, get_filename_and_ext
from cyberdrop_dl.mediaprops import ISO639Subtitle, Resolution
from cyberdrop_dl.models.validators import strings
from cyberdrop_dl.url_objects import AbsoluteHttpURL, MediaItem, MuxVideo, ScrapeItem, is_absolute_http_url
from cyberdrop_dl.utils import css, dates, enter_context, fast_cache, is_blob_or_svg, m3u8, parse_url, unique
from cyberdrop_dl.utils._url import matches_any_host, remove_trailing_slash
from cyberdrop_dl.utils.dataclass import ConfigDataclass, DictDataclass, frozen
from cyberdrop_dl.utils.errors import error_handling_context

if TYPE_CHECKING:
    import datetime
    import http.cookies
    from collections.abc import (
        AsyncGenerator,
        AsyncIterator,
        Awaitable,
        Callable,
        Coroutine,
        Generator,
        Iterable,
        Mapping,
    )

    import yarl
    from bs4 import BeautifulSoup, Tag

    from cyberdrop_dl.clients.response import AbstractResponse
    from cyberdrop_dl.config import Config
    from cyberdrop_dl.database import Database
    from cyberdrop_dl.manager import Manager
    from cyberdrop_dl.progress.scraping import ScrapingUI

logger = logging.getLogger(__name__)


type OneOrTuple[T] = T | tuple[T, ...]
type SupportedPaths = dict[str, OneOrTuple[str]]
type SupportedDomains = OneOrTuple[str]
type DebridURL = Callable[[], Awaitable[AbsoluteHttpURL]] | AbsoluteHttpURL | None

ORIGIN: ContextVar[AbsoluteHttpURL] = ContextVar("ORIGIN")
_CHECK_DL_CAPACITY: ContextVar[bool] = ContextVar("_CHECK_DL_CAPACITY")
_HASH_PREFIXES = "md5:", "sha1:", "sha256:", "xxh128:"


@frozen
class _PlaceHolderConfigInclude:
    file_id: bool = True
    video_codec: bool = True
    audio_codec: bool = True
    resolution: bool = True
    fps: bool = True
    hash: bool = True


_include = _PlaceHolderConfigInclude()


type URLHasher = Callable[[AbsoluteHttpURL], str]


def _path_qs_frag(url: AbsoluteHttpURL) -> str:
    return f"{url.path_qs}#{frag}" if (frag := url.fragment) else url.path_qs


_DB_PATH_BUILDERS: MappingProxyType[str, URLHasher] = MappingProxyType(
    {
        "url": str,
        "name": lambda url: url.name,
        "path": lambda url: url.path,
        "path_qs": lambda url: url.path_qs,
        "path_qs_frag": _path_qs_frag,
        "path_frag": lambda url: f"{url.path}#{frag}" if (frag := url.fragment) else url.path,
    }
)


@frozen(order=True, kw_only=False)
class CrawlerInfo:
    site: str
    primary_url: AbsoluteHttpURL
    scrape_mapper_keys: tuple[str, ...]
    supported_domains: tuple[str, ...]
    supported_paths: dict[str, tuple[str, ...]]

    __iter__ = DictDataclass.__iter__

    def __post_init__(self) -> None:
        try:
            url = remove_trailing_slash(self.primary_url)
        except AttributeError:
            pass
        else:
            object.__setattr__(self, "primary_url", url)

    @classmethod
    def abstract(cls, name: str, site: str, paths: Mapping[str, tuple[str, ...]]) -> Self:
        return cls(site, f"::{name} CRAWLER::", (), (), paths)  # pyright: ignore[reportArgumentType]

    def __json__(self) -> dict[str, Any]:
        me = dict(self)
        me["primary_url"] = str(self.primary_url)
        return me


@frozen(kw_only=False)
class SiteCookies:
    raw: http.cookies.BaseCookie[str]

    def get(self, name: str, /) -> str | None:
        if morsel := self.raw.get(name):
            return morsel.value

    def __getitem__(self, name: str, /) -> str:
        value = self.get(name)
        if value is None:
            raise KeyError(name)
        return value

    def keys(self) -> tuple[str, ...]:
        # dict protocol
        return tuple(self.raw.keys())


class _CrawlerLogger(logging.LoggerAdapter[logging.Logger]):
    def __init__(self, crawler_name: str) -> None:
        self._crawler_name: str = crawler_name
        super().__init__(logger)

    def process(self, msg: object, kwargs: Any) -> tuple[str, Any]:
        return f"[{self._crawler_name}] {msg}", kwargs


@fast_cache
def _get_logger(crawler_name: str) -> _CrawlerLogger:
    return _CrawlerLogger(crawler_name)


@final
@frozen
class URLConfig(ConfigDataclass):
    __attr_name__: ClassVar[str] = "__url_config__"
    trim: bool | None = None
    allow_empty_path: bool | None = None
    ignore_fragment: bool | None = None


@final
@frozen
class DownloadConfig(ConfigDataclass):
    __attr_name__: ClassVar[str] = "__dl_config__"
    slots: int | None = None
    server_lock: bool | None = None
    ignore_content_type: bool | None = None
    impersonate: str | bool | None = None


@URLConfig(trim=True, allow_empty_path=False, ignore_fragment=True)
@HTTPConfig(rate_limit=(25, 1))
@DownloadConfig(slots=None, server_lock=False)
class Crawler(HTTPMixin, HLSMixin, ABC):
    __dl_config__: ClassVar[DownloadConfig]
    __url_config__: ClassVar[URLConfig]
    __http_config__: ClassVar[HTTPConfig]

    DOMAIN: ClassVar[str]
    OLD_DOMAINS: ClassVar[tuple[str, ...]] = ()
    SUPPORTED_DOMAINS: ClassVar[SupportedDomains] = ()
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {}
    DEFAULT_POST_TITLE_FORMAT: ClassVar[str] = "{date} - {id} - {title}"
    NEXT_PAGE_SELECTOR: ClassVar[str] = ""

    FOLDER_DOMAIN: ClassVar[str] = ""
    PRIMARY_URL: ClassVar[AbsoluteHttpURL]
    _FORUM: ClassVar[bool] = False

    disabled: bool = False

    def __repr__(self) -> str:
        fields = (
            f"domain={self.DOMAIN!r}",
            f"primary_url={self.PRIMARY_URL!r}",
            f"disabled={self.disabled!r}",
            f"_ready={self._ready!r}",
        )
        return f"<{type(self).__name__}({', '.join(fields)})>"

    @final
    @staticmethod
    def db_path_builder(key: Literal["url", "name", "path", "path_qs", "path_qs_frag", "path_frag"]):

        def apply[T: Crawler](cls: type[T]) -> type[T]:
            cls.__db_path__ = staticmethod(_DB_PATH_BUILDERS[key])
            return URLConfig(ignore_fragment=not ("frag" in key or key == "url"))(cls)

        return apply

    @staticmethod
    def __db_path__(url: AbsoluteHttpURL, /) -> str:
        return url.path

    @final
    def __init__(self, manager: Manager, task_mng: aio.TaskManager, tui: ScrapingUI) -> None:
        self.manager: Manager = manager

        self._startup_lock: asyncio.Lock = asyncio.Lock()
        self._ready: bool = False
        self._logged_in: bool = False
        self._scraped_items: set[str] = set()
        self._semaphore: asyncio.Semaphore = asyncio.Semaphore(40)
        self.config: Config = manager.config
        self.client: HTTPClient = manager.http_client
        _CHECK_DL_CAPACITY.set(self.config.downloads.back_pressure)
        assert self.__dl_config__.server_lock is not None
        self.downloader: Downloader = Downloader(
            manager,
            use_server_lock=self.__dl_config__.server_lock,
            slots=self.__dl_config__.slots,
        )

        self.__http_ctx__: HTTPContext = HTTPContext.build(self.DOMAIN, self.__http_config__, self.__throttle)
        try:
            self.__http_ctx__.headers.setdefault("Referer", str(self.PRIMARY_URL))
        except AttributeError:
            pass

        self._task_mngr: Final = task_mng
        self.tui: Final = tui

        self.__post_init__()

    def __post_init__(self) -> None:
        """Override in subclasses to add custom init logic

        This method gets called immediately on class creation. This method MUST NOT raise any exception"""

    @final
    async def __async_init__(self) -> None:
        if self._ready:
            return
        async with self._startup_lock:
            if self._ready:
                return

            self.client.limiter[self.DOMAIN] = self.__http_ctx__.rate_limit
            try:
                await self.__async_post_init__()
            except Exception:
                self.log.exception("Async initialization failed. Crawler has been disabled")
                self.tui.scrape_errors.add("Crawler Init Error")
                self.disabled = True
            finally:
                self._ready = True

    async def __async_post_init__(self) -> None:
        """Perform additional setup that requires I/O

        ex: login, getting API tokens, etc..

        This method its called once and only if the crawler is actually going to be scrape something"""

    def __init_subclass__(
        cls, *, is_abc: bool = False, is_generic: bool = False, is_debug: bool = False, **kwargs: Any
    ) -> None:
        assert cls.__name__.endswith("Crawler"), f"{cls.__name__} does not end with 'Crawler'"
        assert cls.__name__ not in Registry.names
        Registry.names.add(cls.__name__)
        try:
            super().__init_subclass__(**kwargs)
        except TypeError as e:
            raise TypeError(f"Unknown kwargs arguments for {cls.__name__}.__init_subclass__(): {kwargs!r}") from e

        _check_init_overrides(cls)
        cls.NAME: str = cls.__name__.removesuffix("Crawler")
        cls.IS_GENERIC: bool = is_generic
        paths = _sort_supported_paths(cls.SUPPORTED_PATHS)
        cls.SUPPORTED_PATHS = paths  # pyright: ignore[reportConstantRedefinition, reportAttributeAccessIssue]
        cls.IS_ABC: bool = is_abc

        add_to_registry = bool(not is_debug or (is_debug and env.ENABLE_DEBUG_CRAWLERS))

        if cls.IS_GENERIC:
            cls.INFO: CrawlerInfo = CrawlerInfo.abstract("GENERIC", cls.NAME, paths)
            if add_to_registry:
                Registry.generic.add(cls)
            return

        if is_abc:
            cls.INFO = CrawlerInfo.abstract("ABC", cls.NAME, paths)  # pyright: ignore[reportConstantRedefinition]
            if add_to_registry:
                Registry.abc.add(cls)
            return

        if cls.NAME != "RealDebrid":
            Crawler._assert_fields_overrides(cls, "PRIMARY_URL", "DOMAIN", "SUPPORTED_PATHS")

        cls.REPLACE_OLD_DOMAINS_REGEX: str | None = "|".join(cls.OLD_DOMAINS) if cls.OLD_DOMAINS else None
        _prepare_supported_domains(cls)
        _validate_supported_paths(cls)

        cls.FOLDER_DOMAIN = cls.FOLDER_DOMAIN or cls.DOMAIN.capitalize()  # pyright: ignore[reportConstantRedefinition]

        scrape_keys = _make_scrape_mapper_keys(cls)
        cls.INFO = CrawlerInfo(  # pyright: ignore[reportConstantRedefinition]
            site=cls.FOLDER_DOMAIN,
            primary_url=cls.PRIMARY_URL,
            supported_domains=_make_wiki_supported_domains(scrape_keys),
            scrape_mapper_keys=scrape_keys,
            supported_paths=paths,
        )
        if add_to_registry:
            Registry.concrete.add(cls)

    async def __throttle(self) -> None:
        if _CHECK_DL_CAPACITY.get():
            await self.downloader.capacity.wait(self.FOLDER_DOMAIN)

    def __json_resp_check__(self, json_resp: Any, resp: AbstractResponse[Any], /) -> None:
        """Custom check for JSON responses.

        This method is called automatically by the `HttpClient` when a JSON response is received from `cls.DOMAIN`
        and it was **NOT** successful (`4xx` or `5xx` HTTP code).

        Override this method in subclasses to raise a custom `ScrapeError` instead of the default HTTP error

        Example:
            ```python
            if isinstance(json, dict) and json.get("status") == "error":
                raise ScrapeError(422, f"API error: {json['message']}")
            ```

        IMPORTANT:
            Cases were the response **IS** successful (200, OK) but the JSON indicates an error
            should be handled by the crawler itself
        """

    @final
    @staticmethod
    def _assert_fields_overrides(subclass: type[Crawler], *fields: str) -> None:
        for field_name in fields:
            assert getattr(subclass, field_name, None), f"Subclass {subclass.__name__} must override: {field_name}"

    @final
    @property
    def database(self) -> Database:
        return self.manager.database

    @final
    @property
    def cache(self) -> TTLCacheAdapter[Any]:
        """Get a TTL cache access for entries specific to this crawler

        NOTE: cached values MUST be JSON seriable"""
        return TTLCacheAdapter(self.manager.cache, ("crawlers", self.DOMAIN))

    @final
    def create_task(self, coro: Coroutine[Any, Any, Any]) -> None:
        """Use for coros that need to make HTTP requests

        They will skip 1 loop iteration"""
        _ = self._task_mngr.scrape.create_lazy_task(coro)

    @final
    def create_eager_task(self, coro: Coroutine[Any, Any, Any]) -> None:
        """Run this coro as soon as possible"""
        _ = self._task_mngr.scrape.create_eager_task(coro)

    @abstractmethod
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Here goes the main logic to parse URL paths.

        This method MUST NOT raise any exceptions other that ValueError to indicate that the path is not supported"""

    @final
    @property
    def log(self) -> _CrawlerLogger:
        return self.get_logger()

    @final
    @classmethod
    def get_logger(cls, name: str | None = None):
        return _get_logger(name or cls.FOLDER_DOMAIN)

    @final
    @property
    def waiting_items(self) -> int:
        if self._semaphore._waiters is None:
            return 0
        return len(self._semaphore._waiters)

    @final
    @property
    def origin(self) -> AbsoluteHttpURL:
        return ORIGIN.get()

    @property
    def separate_posts(self) -> bool:
        return self.config.subfolders.separate_posts.enabled

    @final
    @contextlib.contextmanager
    def disable_on_error(self, msg: str) -> Generator[None]:
        try:
            yield
        except Exception:
            self.log.error(f"{msg}. Crawler has been disabled")
            self.disabled = True
            raise

    catch_errors: Final = error_handling_context

    @final
    async def run(self, scrape_item: ScrapeItem, *, check_referer: bool = False) -> None:
        if self.disabled:
            return

        with scrape_item.track_changes:
            scrape_item.url = url = self.transform_url(scrape_item.url)

        lookup = url.path_qs if self.__url_config__.ignore_fragment else _path_qs_frag(url)
        if lookup in self._scraped_items:
            logger.info(f"Skipping {url} as it has already been scrapped")
            return

        self._scraped_items.add(lookup)

        if not self.__url_config__.allow_empty_path and url.path == "/":
            self.raise_exc(scrape_item, ScrapeError.unsupported())
            return

        if check_referer and await self.check_complete_from_referer(url):
            return

        async with self._semaphore:
            with self.new_task_id(scrape_item.url):
                try:
                    await self.fetch(scrape_item)
                except ValueError:
                    self.raise_exc(scrape_item, ScrapeError.unsupported())
                except MaxChildrenError as e:
                    self.raise_exc(scrape_item, e)

    @classmethod
    def transform_url(cls, url: AbsoluteHttpURL) -> AbsoluteHttpURL:
        """Transforms an URL before it reaches the fetch method

        Override it to transform thumbnail URLs into full res URLs or URLs in an old unsupported format into a new one"""
        if cls.REPLACE_OLD_DOMAINS_REGEX is not None:
            new_host = re.sub(cls.REPLACE_OLD_DOMAINS_REGEX, cls.PRIMARY_URL.host, url.host)
            return url.with_host(new_host)
        return url

    def raise_exc(self, scrape_item: ScrapeItem, exc: type[Exception] | Exception | str | int) -> None:
        with self.catch_errors(scrape_item):
            if isinstance(exc, (str, int)):
                exc = ScrapeError(exc)
            raise exc

    @final
    def new_task_id(self, url: AbsoluteHttpURL):
        """Creates a new task_id (shows the URL in the UI and logs)"""
        self.log.info(f"Scraping {url}")
        _ = ORIGIN.set(url.origin())
        return self.tui.scrape.new(url)

    @final
    @staticmethod
    def is_subdomain(url: AbsoluteHttpURL) -> bool:
        return url.host.removeprefix("www.").count(".") > 1

    @final
    async def write_metadata(self, scrape_item: ScrapeItem, name: str, metadata: object) -> None:
        """Write general metadata (not specific to a single file) to json output"""

        media_item = MediaItem(
            url=AbsoluteHttpURL(scrape_item.url.with_scheme("metadata")),
            domain=self.DOMAIN,
            download_folder=_prepare_download_path(scrape_item, self.FOLDER_DOMAIN),
            filename=f"{name}.metadata",  # we won't write to fs, so we skip name sanitization
            db_path="",
            referer=scrape_item.url,
            album_id=scrape_item.album_id,
            parents=tuple(scrape_item.parents),
            uploaded_at=scrape_item.uploaded_at,
        )
        media_item.metadata = metadata
        await self.__write_to_jsonl(media_item)

    @final
    async def handle_file(  # noqa: PLR0913
        self,
        url: AbsoluteHttpURL,
        scrape_item: ScrapeItem,
        filename: str,
        /,
        ext: str | None = None,
        *,
        custom_filename: str | None = None,
        debrid_link: DebridURL = None,
        m3u8: m3u8.Rendition | MuxVideo | None = None,
        metadata: object = None,
        referer: AbsoluteHttpURL | None = None,
        frag: str | None = None,
        thumbnail: AbsoluteHttpURL | str | None = None,
        headers: Mapping[str, str] | None = None,
        uploaded_at: int | None = None,
    ) -> None:
        """Creates a MediaItem and hands it off to the downloader.

        Referer is the referer to use for the db, not the actual HTTP referer"""

        referer = referer or scrape_item.url
        if frag:
            referer = referer.with_fragment(f"{referer.fragment} - {frag}" if referer.fragment else frag)

        media_item = MediaItem(
            url=url,
            domain=self.DOMAIN,
            download_folder=_prepare_download_path(scrape_item, self.FOLDER_DOMAIN),
            filename=custom_filename or filename,
            db_path=self.__db_path__(url),
            referer=referer,
            album_id=scrape_item.album_id,
            ext=ext or Path(filename).suffix,
            original_filename=filename,
            parents=tuple(scrape_item.parents),
            uploaded_at=uploaded_at or scrape_item.uploaded_at,
            debrid_url=_prepare_debrid_url(debrid_link),
            json_check=self.__json_resp_check__,
        )

        if media_item.ext not in FileExt.MEDIA:
            thumbnail = None

        elif thumbnail is not None and type(thumbnail) is not AbsoluteHttpURL:
            thumbnail = self.parse_url(thumbnail)

        media_item.thumbnail = thumbnail
        media_item.headers.update(self._prepare_headers(scrape_item))
        if headers:
            media_item.headers.update(headers)

        if metadata:
            media_item.metadata = metadata

        check_path_traversal(self.config.download_folder, media_item.download_folder)
        check_dangerous_filename(media_item.download_filename or media_item.filename)
        await self.handle_media_item(media_item, m3u8)

        if thumbnail and self.config.filters.files.thumbnails:
            with self.catch_errors(thumbnail):
                ext = await self._thumb_ext(thumbnail)
                thumb_name = f"{Path(media_item.filename).stem}_thumb{ext}"
                filename, _ = self.get_filename_and_ext(thumb_name)
                await self.handle_file(
                    thumbnail,
                    scrape_item,
                    thumb_name,
                    ext,
                    custom_filename=filename,
                    frag="thumbnail",
                )

    async def _thumb_ext(self, thumbnail: AbsoluteHttpURL) -> str:
        try:
            _, ext = self.get_filename_and_ext(thumbnail.name)
        except NoExtensionError:
            async with self.request(thumbnail, "HEAD") as resp:
                _, ext = self.get_filename_and_ext(thumbnail.name, mime_type=resp.content_type)
        return ext

    def _prepare_headers(self, scrape_item: ScrapeItem) -> dict[str, str]:
        return {
            "User-Agent": self.__http_ctx__.headers.get(hdrs.USER_AGENT) or self.config.network.user_agent,
            "Referer": str(scrape_item.url),
        }

    @final
    async def _download(
        self, media_item: MediaItem, streams: m3u8.Rendition | MuxVideo | None, *, skip: bool = False
    ) -> None:
        if self.__dl_config__.impersonate is not None:
            media_item.extra_info["impersonate"] = self.__dl_config__.impersonate

        try:
            if skip or SKIP_DOWNLOAD.get():
                return

            await self.downloader.run(media_item, streams)

        finally:
            await self.__write_to_jsonl(media_item)

    async def __write_to_jsonl(self, media_item: MediaItem) -> None:
        if not self.config.dump_json:
            return

        await self.manager.scrape_mapper.logs.write_jsonl([media_item.serialize()])

    @final
    async def check_complete(self, url: AbsoluteHttpURL, referer: AbsoluteHttpURL | None = None) -> bool:
        """Checks if this URL has been download before.

        This method is called automatically on a created media item,
        but Crawler code can use it to skip unnecessary requests"""

        db_path = self.__db_path__(url)
        current_referer, downloaded = await self.database.history.check_complete(self.DOMAIN, db_path)
        if downloaded:
            logger.info("Skipping %s as it has already been downloaded", url)
            self.tui.files.stats.prev_completed += 1

            if referer and url != referer and str(referer) != current_referer:
                # Update the referer if it has changed so that check_complete_by_referer can work
                logger.info("Updating referer of %s from %s to %s", url, current_referer, referer)
                await self.database.history.update_referer(self.DOMAIN, db_path, referer)

        return downloaded

    def _prepare_media_item(self, media_item: MediaItem) -> None:
        # To override by subclasses
        assert media_item

    async def handle_media_item(self, media_item: MediaItem, streams: m3u8.Rendition | MuxVideo | None = None) -> None:
        self._prepare_media_item(media_item)
        with (
            enter_context(IGNORE_CONTENT_TYPE, True)
            if self.__dl_config__.ignore_content_type
            else contextlib.nullcontext()
        ):
            self._task_mngr.downloads.create_task(
                self._download(media_item, streams, skip=await self.__should_skip(media_item))
            )

    async def __should_skip(self, media_item: MediaItem) -> bool:
        if await self.check_complete(media_item.url, media_item.referer):
            if media_item.album_id:
                await self.database.history.set_album_id(self.DOMAIN, media_item)
            return True

        if _should_skip_by_config(media_item, self.config):
            self.tui.files.stats.skipped += 1
            return True

        return False

    @final
    async def check_complete_from_referer(
        self: Crawler, referer: AbsoluteHttpURL, *, any_crawler: bool = False
    ) -> bool:
        """Checks if the scrape item has already been scraped.

        if `any_crawler` is `True`, checks database entries for all crawlers and returns `True` if at least 1 of them has marked it as completed
        """
        domain = None if any_crawler else self.DOMAIN
        downloaded = await self.database.history.check_complete_by_referer(domain, referer)
        if downloaded:
            logger.info(f"Skipping {referer} as it has already been downloaded")
            self.tui.files.stats.prev_completed += 1
        return downloaded

    @final
    async def check_complete_by_hash(
        self: Crawler, url: AbsoluteHttpURL, hash_algo: Literal["md5", "sha256"], checksum: str
    ) -> bool:
        """Returns `True` if at least 1 file with this hash is recorded on the database"""
        if self.config.ignore_hashes:
            return False

        expected_len = 32 if hash_algo == "md5" else 64
        if len(checksum) != expected_len:
            self.log.warning(
                "Hash %s with %s characters does not match the expected size for a %s hex digest (%s characters), ignoring...",
                checksum,
                len(checksum),
                hash_algo,
                expected_len,
            )
            return False

        downloaded = await self.database.hash.check_hash_exists(hash_algo, checksum)
        if downloaded:
            logger.info(f"Skipping {url} as its hash ({hash_algo}:{checksum}) has already been downloaded")
            self.tui.files.stats.prev_completed += 1
        return downloaded

    @final
    async def get_album_results(self, album_id: str) -> dict[str, bool]:
        """Checks whether an album has completed given its domain and album id."""
        return await self.database.history.query_album(self.DOMAIN, album_id)

    @final
    def handle_external_links(self, scrape_item: ScrapeItem, *, reset: bool = True) -> None:
        """Maps external links to the scraper class."""
        if reset:
            scrape_item.reset()
        self.create_task(self.manager.scrape_mapper.send_to_crawler(scrape_item))

    @final
    def handle_embed(self, scrape_item: ScrapeItem) -> None:
        self.handle_external_links(scrape_item, reset=False)

    @final
    @classmethod
    def get_filename_and_ext(
        cls,
        filename: str,
        *,
        assume_ext: str | None = ".mp4",
        mime_type: str | None = None,
    ) -> tuple[str, str]:
        """Wrapper around `utils.get_filename_and_ext`.
        Calls it as is.
        If that fails, appends `assume_ext` and tries again, but only if the user had exclude_files_with_no_extension = `False`
        """
        try:
            return get_filename_and_ext(filename, mime_type, xenforo=cls._FORUM)
        except NoExtensionError:
            if ALLOW_NO_EXT.get() and assume_ext:
                return get_filename_and_ext(filename + assume_ext, mime_type, xenforo=cls._FORUM)
            raise

    @final
    def check_album_results(self, url: AbsoluteHttpURL, album_results: Mapping[str, bool]) -> bool:
        """Checks whether an album has completed given its domain and album id."""
        if not album_results:
            return False

        url_path = self.__db_path__(url)
        if album_results.get(url_path) is True:
            logger.info(f"Skipping {url} as it has already been downloaded")
            self.tui.files.stats.prev_completed += 1
            return True
        return False

    @final
    def create_title(
        self, title: str, album_id: str | None = None, thread_id: int | None = None, *, force_album_id: bool = False
    ) -> str:
        """Creates the title for the scrape item."""
        return compose_title(
            self.config,
            self.FOLDER_DOMAIN,
            title,
            album_id,
            thread_id,
            force_album_id=force_album_id,
        )

    @final
    def create_separate_post_title(
        self,
        title: str | None = None,
        id: str | None = None,  # noqa: A002
        date: datetime.datetime | datetime.date | float | None = None,
        /,
    ) -> str:
        if not self.separate_posts:
            return ""
        title_format = self.config.subfolders.separate_posts.format
        if title_format.strip().casefold() == "{default}":
            title_format = self.DEFAULT_POST_TITLE_FORMAT
        if isinstance(date, (float, int)):
            date = dates.from_timestamp(date)

        post_title, _ = strings.safe_format(title_format, id=id, number=id, date=date, title=title)
        return post_title

    @classmethod
    def parse_url(
        cls,
        url: yarl.URL | str,
        /,
        relative_to: AbsoluteHttpURL | None = None,
        *,
        trim: bool | None = None,
    ) -> AbsoluteHttpURL:
        """Wrapper around `utils.parse_url` to use `self.PRIMARY_URL` as base"""
        base = relative_to or cls.PRIMARY_URL
        assert is_absolute_http_url(base)
        if trim is None:
            trim = cls.__url_config__.trim
        if trim is None:
            trim = True
        return parse_url(url, base, trim=trim)

    @final
    @property
    def cookies(self) -> SiteCookies:
        return SiteCookies(self.client.cookies.filter_cookies(self.PRIMARY_URL))

    @final
    def update_cookies(self, cookies: dict[str, Any], url: yarl.URL | None = None) -> None:
        """Update cookies for the provided URL

        If `url` is `None`, defaults to `self.PRIMARY_URL`
        """
        response_url = url or self.PRIMARY_URL
        self.client.cookies.update_cookies(cookies, response_url)

    @final
    @classmethod
    def iter_urls(
        cls, tag: Tag, selector: str, attribute: str = "href", origin: AbsoluteHttpURL | None = None
    ) -> Generator[AbsoluteHttpURL]:
        for url in unique(css.iselect(tag, selector, attribute)):
            if not is_blob_or_svg(url):
                yield cls.parse_url(url, origin)

    @final
    async def make_album_checker(self, album_id: str) -> Callable[[AbsoluteHttpURL], bool]:
        results = await self.get_album_results(album_id)

        def should_download(url: AbsoluteHttpURL) -> bool:
            return not self.check_album_results(url, results)

        return should_download

    @final
    def iter_children(
        self,
        scrape_item: ScrapeItem,
        soup: BeautifulSoup,
        selector: str,
        /,
        attribute: str = "href",
    ) -> Generator[ScrapeItem]:
        return scrape_item.create_children(self.iter_urls(soup, selector, attribute))

    async def web_pager(
        self,
        url: AbsoluteHttpURL,
        selector: Callable[[BeautifulSoup], yarl.URL | str | None] | str | None = None,
        *,
        impersonate: str | bool | None = False,
        relative_to: AbsoluteHttpURL | None = None,
        trim: bool | None = None,
    ) -> AsyncIterator[BeautifulSoup]:
        """Generator of website pages"""

        relative_to = relative_to or url
        page_url = url
        if callable(selector):
            get_next_page = selector

        else:
            selector = selector or self.NEXT_PAGE_SELECTOR
            assert selector, f"No selector was provided and {self.DOMAIN} does define a next_page_selector"

            def get_next_page(soup: BeautifulSoup, /) -> yarl.URL | str | None:
                try:
                    return css.select(soup, selector, "href")
                except css.SelectorError:
                    return None

        while True:
            soup = await self.request_soup(page_url, impersonate=impersonate or None)
            yield soup
            page_url_str = get_next_page(soup)
            if not page_url_str:
                break
            page_url = self.parse_url(page_url_str, relative_to=relative_to, trim=trim)

    async def direct_file(
        self, scrape_item: ScrapeItem, /, url: AbsoluteHttpURL | None = None, assume_ext: str | None = None
    ) -> None:
        """Download a direct link file. Filename will be the url slug"""
        url = url or scrape_item.url
        with self.catch_errors(url):
            filename, ext = self.get_filename_and_ext(url.name or url.parent.name, assume_ext=assume_ext)
            await self.handle_file(url, scrape_item, filename, ext)

    @final
    @contextlib.asynccontextmanager
    async def new_task_group(self) -> AsyncGenerator[aio.EagerTaskGroup]:
        """A taskgroup that does not cancel its tasks if an exception is raised within its `async with` context

        Exceptions raised within a task will still cancel all tasks

        This is mostly just to catch `MaxChildrenError`"""

        context_exc = None
        task_exc = None

        try:
            async with aio.EagerTaskGroup() as tg:
                try:
                    yield tg
                except Exception as e:  # noqa: BLE001
                    context_exc = e
        except ExceptionGroup as eg:
            if context_exc is None:
                raise
            task_exc = eg

        try:
            if task_exc is not None and context_exc is not None:
                raise ExceptionGroup(task_exc.message, (*task_exc.exceptions, context_exc)) from None
            if task_exc is not None:
                raise task_exc from None
            if context_exc is not None:
                raise context_exc from None
        finally:
            context_exc = task_exc = None

    @final
    @classmethod
    def parse_date(cls, date_or_datetime: str, /, format: str) -> float:  # noqa: A002
        return dates.parse_format(date_or_datetime, format).timestamp()

    @final
    @classmethod
    def parse_iso_date(cls, date_or_datetime: str, /) -> float:
        return dates.parse_iso(date_or_datetime).timestamp()

    @final
    async def follow_redirect(self, scrape_item: ScrapeItem) -> None:
        with self.catch_errors(scrape_item):
            redirect = await self.request_redirect(scrape_item.url)
            if scrape_item.url == redirect:
                raise ScrapeError(422, "Infinite redirect")
            if (password := scrape_item.url.query.get("password")) and "password" not in redirect.query:
                redirect = redirect.update_query(password=password)
            scrape_item.url = redirect
            self.create_task(self.run(scrape_item))

    @final
    def create_custom_filename(  # noqa: PLR0913
        self,
        name: str,  # can be the full name or just the stem
        ext: str,
        /,
        *,
        file_id: str | None = None,
        video_codec: str | None = None,
        audio_codec: str | None = None,
        resolution: Resolution | str | int | None = None,
        fps: float | None = None,
        hash_string: str | None = None,
    ) -> str:

        def extra_info() -> Generator[str]:
            if _include.file_id and file_id:
                yield file_id
            if _include.video_codec and video_codec:
                yield video_codec
            if _include.audio_codec and audio_codec:
                yield audio_codec

            if _include.resolution and resolution and resolution not in {Resolution.highest(), Resolution.unknown()}:
                res = resolution if type(resolution) is Resolution else Resolution.parse(resolution)
                if fps and _include.fps:
                    yield res.name + "@" + (str(int(fps)) if fps.is_integer() else f"{fps:.1f}") + "fps"
                else:
                    yield res.name

            if _include.hash and hash_string:
                assert any(hash_string.startswith(x) for x in _HASH_PREFIXES), f"Invalid: {hash_string = }"
                yield hash_string

        return compose_filename(name, ext, *extra_info())

    @final
    def handle_subs(self, scrape_item: ScrapeItem, video_filename: str, subtitles: Iterable[ISO639Subtitle]) -> None:
        counter: Counter[str] = Counter()
        video_stem = Path(video_filename).stem
        for sub in subtitles:
            link = self.parse_url(sub.url)
            counter[sub.lang_code] += 1
            if (count := counter[sub.lang_code]) > 1:
                suffix = f"{sub.lang_code}.{count}{link.suffix}"
            else:
                suffix = f"{sub.lang_code}{link.suffix}"

            sub_name, ext = self.get_filename_and_ext(f"{video_stem}.{suffix}")
            new_scrape_item = scrape_item.create_new(scrape_item.url.with_fragment(sub_name))
            self.create_eager_task(
                self.handle_file(
                    link,
                    new_scrape_item,
                    sub.name or link.name,
                    ext,
                    custom_filename=sub_name,
                )
            )

    async def generic_m3u8(self, scrape_item: ScrapeItem, url: AbsoluteHttpURL | None = None) -> None:
        url = url or scrape_item.url
        referer = scrape_item.get_referer()
        with self.catch_errors(url):
            if referer and await self.check_complete_from_referer(referer):
                return

            if await self.check_complete(url):
                return

            headers = {"Referer": str(referer)} if referer else {}
            m3u8, info = await self.request_m3u8(url, headers=headers)
            name = url.name or url.parent.name
            filename = self.create_custom_filename(
                url.path,
                ext := ".mp4",
                resolution=info and info.resolution,
                video_codec=info and info.codecs.video,
                audio_codec=info and info.codecs.audio,
            )
            await self.handle_file(
                url,
                scrape_item,
                name,
                ext,
                m3u8=m3u8,
                custom_filename=filename,
            )


@HTTPConfig(rate_limit=(25, 1))
class API(HTTPMixin, ABC):
    PRIMARY_URL: AbsoluteHttpURL = AbsoluteHttpURL()
    # We inherit from ABC to force type checkers to recognize attributes defined in __post_init__ as if they were defined in __init__
    #
    log: _CrawlerLogger

    class Endpoint[T: API](ABC):  # noqa: B024
        def __init__(self, api: T) -> None:
            self.api: T = api
            self.__post_init__()

        def __post_init__(self) -> None: ...  # noqa: B027

        def __repr__(self) -> str:
            return f"<{type(self).__name__}>"

    @final
    def __init__(
        self,
        domain: str,
        config: Config,
        cache: TTLCacheAdapter[Any],
        client: HTTPClient,
        ctx: HTTPContext | None = None,
    ) -> None:
        self.config: Final = config
        self.cache: Final = cache
        self.client: HTTPClient = client
        self.__http_ctx__: HTTPContext = ctx or HTTPContext.build(domain, self.__http_config__)
        self.__post_init__()

    @classmethod
    def parse_url(
        cls,
        url: yarl.URL | str,
        /,
        relative_to: AbsoluteHttpURL | None = None,
        *,
        trim: bool | None = None,
    ) -> AbsoluteHttpURL:
        """Wrapper around `utils.parse_url` to use `self.PRIMARY_URL` as base"""
        base = relative_to or cls.PRIMARY_URL
        assert is_absolute_http_url(base)
        if trim is None:
            trim = True
        return parse_url(url, base, trim=trim)

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        config = crawler.__http_config__ | cls.__http_config__
        self = cls(
            domain=crawler.DOMAIN,
            cache=crawler.cache,
            client=crawler.client,
            config=crawler.manager.config,
            ctx=HTTPContext.build(crawler.DOMAIN, config, crawler.__http_ctx__.throttle),
        )
        self.PRIMARY_URL = crawler.PRIMARY_URL  # pyright: ignore[reportConstantRedefinition]
        self.parse_url = crawler.parse_url
        self.log = crawler.log
        self.__http_config__ = config  # pyright: ignore[reportAttributeAccessIssue]
        try:
            self.__http_ctx__.headers.setdefault("Referer", str(self.PRIMARY_URL))
        except AttributeError:
            pass
        return self

    def __post_init__(self) -> None: ...

    def __repr__(self) -> str:
        return f"<{type(self).__name__}({self.PRIMARY_URL!r})>"

    @final
    @property
    def origin(self) -> AbsoluteHttpURL:
        return ORIGIN.get()


def _make_scrape_mapper_keys(cls: type[Crawler] | Crawler) -> tuple[str, ...]:
    hosts = cls.SUPPORTED_DOMAINS or cls.DOMAIN
    if isinstance(hosts, str):
        hosts = (hosts,)
    return tuple(sorted({host.removeprefix("www.") for host in hosts}))


def _prepare_supported_domains(cls: type[Crawler]) -> None:
    if not cls.OLD_DOMAINS:
        return
    supported_domains = cls.SUPPORTED_DOMAINS or ()
    if isinstance(supported_domains, str):
        supported_domains = (supported_domains,)

    cls.SUPPORTED_DOMAINS = tuple(sorted({*cls.OLD_DOMAINS, *supported_domains, cls.PRIMARY_URL.host}))


def _check_init_overrides(cls: type[Crawler]) -> None:
    assert cls.__init__ is Crawler.__init__, (
        f"Subclass {cls.__name__} must not override __init__,use __post_init__ for additional setup"
    )

    assert cls.__async_init__ is Crawler.__async_init__, (
        f"Subclass {cls.__name__} must not override __async_init__,"
        "use __async_post_init__ for setup that requires manipulating cookies or any IO (database access, HTTP requests, etc...)"
    )


def _validate_supported_paths(cls: type[Crawler]) -> None:
    for path_name, paths in cls.SUPPORTED_PATHS.items():
        assert path_name, f"{cls.__name__}, Invalid path: {path_name}"
        assert isinstance(paths, str | tuple), f"{cls.__name__}, Invalid path {path_name}: {type(paths)}"
        if path_name != "Direct links":
            assert paths, f"{cls.__name__} has not paths for {path_name}"

        if path_name.startswith("*"):  # note
            continue

        if isinstance(paths, str):
            paths = (paths,)

        for path in paths:
            assert "`" not in path, f"{cls.__name__}, Invalid path {path_name}: {path}"


def _make_wiki_supported_domains(scrape_mapper_keys: tuple[str, ...]) -> tuple[str, ...]:
    def generalize(domain: str) -> str:
        if "." not in domain:
            return f"{domain}.*"
        return domain

    return tuple(sorted(generalize(domain) for domain in scrape_mapper_keys))


def _sort_supported_paths(supported_paths: SupportedPaths) -> dict[str, tuple[str, ...]]:
    def try_sort(value: OneOrTuple[str]) -> tuple[str, ...]:
        if isinstance(value, tuple):
            return tuple(sorted(value))
        return (value,)

    path_pairs = ((key, try_sort(value)) for key, value in supported_paths.items())
    return dict(sorted(path_pairs, key=lambda x: x[0].casefold()))


def auto_task_id[CrawlerT: Crawler, **P, R](
    func: Callable[Concatenate[CrawlerT, ScrapeItem, P], Coroutine[None, None, R]],
) -> Callable[Concatenate[CrawlerT, ScrapeItem, P], Coroutine[None, None, R]]:
    """Autocreate a new `task_id` from the scrape_item of the method"""

    @functools.wraps(func)
    async def wrapper(self: CrawlerT, scrape_item: ScrapeItem, *args: P.args, **kwargs: P.kwargs) -> R:
        with self.new_task_id(scrape_item.url):
            return await func(self, scrape_item, *args, **kwargs)

    return wrapper


def _should_skip_by_config(media_item: MediaItem, config: Config) -> bool:
    filters = config.filters

    if (hosts := filters.skip_hosts) and matches_any_host(media_item.url, hosts):
        logger.info(f"Download skipped {media_item.url} due to skip_hosts config")
        return True

    if (hosts := filters.only_hosts) and not matches_any_host(media_item.url, hosts):
        logger.info(f"Download skipped {media_item.url} due to only_hosts config")
        return True

    if (regex := filters.filename_regex) and not regex.search(media_item.filename):
        logger.info(
            "Download skipped %s due to filename regex filter. Filename '%s' does not match regex",
            media_item.url,
            media_item.filename,
        )
        return True

    if (regex := filters.filename_regex_exclude) and regex.search(media_item.filename):
        logger.info(
            "Download skipped %s due to filename regex exclude filter. Filename '%s' matched config regex",
            media_item.url,
            media_item.filename,
        )
        return True

    return False


def _prepare_download_path(item: ScrapeItem, domain: str) -> Path:
    path = item.download_folder / item.path
    if item.is_loose_file:
        path = path / f"Loose Files ({domain})"
    return path


def compose_title(  # noqa: PLR0913
    config: Config,
    domain: str,
    title: str,
    album_id: str | None = None,
    thread_id: int | None = None,
    *,
    force_album_id: bool = False,
) -> str:
    title = (title or "Untitled").strip()

    if album_id and (force_album_id or config.subfolders.include.album_id):
        title = f"{title} {album_id}"

    if thread_id and config.subfolders.include.thread_id:
        title = f"{title} {thread_id}"

    if config.subfolders.include.domain:
        title = f"{title} ({domain})"

    # Remove double spaces
    return " ".join(title.split(" "))


def compose_ep_name(season: int | None, ep: int | None, name: str | None) -> str:
    prefix = ""
    if season is not None:
        prefix += f"S{season:02}"
    if ep is not None:
        prefix += f"E{ep:03}"

    name = " - ".join(filter(None, (prefix, name)))
    if not name:
        raise ValueError("Empty episode title")
    return name


def _prepare_debrid_url(debrid_url: DebridURL) -> DebridURL:
    if callable(debrid_url):
        request_dl_url = debrid_url

        async def debrid_url() -> AbsoluteHttpURL:
            with enter_context(_CHECK_DL_CAPACITY, False):
                return await request_dl_url()

    return debrid_url
