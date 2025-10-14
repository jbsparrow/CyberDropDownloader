from __future__ import annotations

import asyncio
import contextlib
import datetime
import inspect
import re
import warnings
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from functools import partial, wraps
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, Concatenate, Literal, NamedTuple, ParamSpec, TypeAlias, TypeVar, final

import yarl
from aiolimiter import AsyncLimiter
from yarl import URL

from cyberdrop_dl import constants
from cyberdrop_dl.clients.scraper_client import ScraperClient
from cyberdrop_dl.data_structures.mediaprops import Resolution
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL, MediaItem, ScrapeItem, copy_signature
from cyberdrop_dl.downloader.downloader import Downloader
from cyberdrop_dl.exceptions import MaxChildrenError, NoExtensionError, ScrapeError
from cyberdrop_dl.scraper import filters
from cyberdrop_dl.utils import css, m3u8
from cyberdrop_dl.utils.dates import TimeStamp, parse_human_date, to_timestamp
from cyberdrop_dl.utils.logger import log, log_debug
from cyberdrop_dl.utils.strings import safe_format
from cyberdrop_dl.utils.utilities import (
    error_handling_wrapper,
    get_download_path,
    get_filename_and_ext,
    is_absolute_http_url,
    is_blob_or_svg,
    parse_url,
    remove_file_id,
    remove_trailing_slash,
    sanitize_filename,
    truncate_str,
)

P = ParamSpec("P")
R = TypeVar("R")
T = TypeVar("T")
_T_co = TypeVar("_T_co", covariant=True)


if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Awaitable, Callable, Coroutine, Generator, Iterable
    from http.cookies import BaseCookie

    from aiohttp_client_cache.response import AnyResponse
    from bs4 import BeautifulSoup, Tag
    from rich.progress import TaskID

    from cyberdrop_dl.clients.response import AbstractResponse
    from cyberdrop_dl.managers.manager import Manager


OneOrTuple: TypeAlias = T | tuple[T, ...]
SupportedPaths: TypeAlias = dict[str, OneOrTuple[str]]
SupportedDomains: TypeAlias = OneOrTuple[str]
RateLimit = tuple[float, float]


HASH_PREFIXES = "md5:", "sha1:", "sha256:", "xxh128:"
VALID_RESOLUTION_NAMES = "4K", "8K", "HQ", "Unknown"


@dataclass(slots=True, frozen=True)
class PlaceHolderConfig:
    include_file_id: bool = True
    include_video_codec: bool = True
    include_audio_codec: bool = True
    include_resolution: bool = True
    include_hash: bool = True


_placeholder_config = PlaceHolderConfig()


class CrawlerInfo(NamedTuple):
    site: str
    primary_url: URL
    supported_domains: tuple[str, ...]
    supported_paths: SupportedPaths


class Crawler(ABC):
    OLD_DOMAINS: ClassVar[tuple[str, ...]] = ()
    SUPPORTED_DOMAINS: ClassVar[SupportedDomains] = ()
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {}
    DEFAULT_POST_TITLE_FORMAT: ClassVar[str] = "{date} - {id} - {title}"

    UPDATE_UNSUPPORTED: ClassVar[bool] = False
    SKIP_PRE_CHECK: ClassVar[bool] = False
    NEXT_PAGE_SELECTOR: ClassVar[str] = ""

    DEFAULT_TRIM_URLS: ClassVar[bool] = True
    FOLDER_DOMAIN: ClassVar[str] = ""
    DOMAIN: ClassVar[str]
    PRIMARY_URL: ClassVar[AbsoluteHttpURL]

    _RATE_LIMIT: ClassVar[RateLimit] = 25, 1
    _DOWNLOAD_SLOTS: ClassVar[int | None] = None

    @copy_signature(ScraperClient._request)
    @contextlib.asynccontextmanager
    async def request(self, *args, **kwargs) -> AsyncGenerator[AbstractResponse]:
        async with self.client._limiter(self.DOMAIN), self.client._request(*args, **kwargs) as resp:
            yield resp

    @copy_signature(ScraperClient._request)
    async def request_json(self, *args, **kwargs) -> Any:
        async with self.request(*args, **kwargs) as resp:
            return await resp.json()

    @copy_signature(ScraperClient._request)
    async def request_soup(self, *args, **kwargs) -> BeautifulSoup:
        async with self.request(*args, **kwargs) as resp:
            return await resp.soup()

    @copy_signature(ScraperClient._request)
    async def request_text(self, *args, **kwargs) -> str:
        async with self.request(*args, **kwargs) as resp:
            return await resp.text()

    @final
    def __init__(self, manager: Manager) -> None:
        self.manager = manager
        self.downloader: Downloader = field(init=False)
        self.client: ScraperClient = field(init=False)
        self.startup_lock = asyncio.Lock()
        self.ready: bool = False
        self.disabled: bool = False
        self.logged_in: bool = False
        self.scraped_items: set[str] = set()
        self.RATE_LIMIT = AsyncLimiter(*self._RATE_LIMIT)
        self.waiting_items = 0
        self.log = log
        self.log_debug = log_debug
        self._semaphore = asyncio.Semaphore(20)
        self.__post_init__()

    @final
    def create_task(self, coro: Coroutine[Any, Any, _T_co]) -> asyncio.Task[_T_co]:
        return self.manager.task_group.create_task(coro)

    def __post_init__(self) -> None: ...  # noqa: B027

    @final
    def _register_response_checks(self) -> None:
        if self._json_response_check.__func__ is Crawler._json_response_check.__func__:
            return

        for host in (self.DOMAIN, self.PRIMARY_URL.host):
            self.client.client_manager._json_response_checks[host] = self._json_response_check

    @classmethod
    def _json_response_check(cls, json_resp: Any) -> None:
        """Custom check for JSON responses.

        This method is called automatically by the `client_manager` when a JSON response is received from `cls.DOMAIN`
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
        raise NotImplementedError

    @final
    @staticmethod
    def _assert_fields_overrides(subclass: type[Crawler], *fields: str):
        for field_name in fields:
            assert getattr(subclass, field_name, None), f"Subclass {subclass.__name__} must override: {field_name}"

    def __init_subclass__(
        cls, is_abc: bool = False, is_generic: bool = False, generic_name: str = "", **kwargs
    ) -> None:
        super().__init_subclass__(**kwargs)

        msg = (
            f"Subclass {cls.__name__} must not override __init__ method,"
            "use __post_init__ for additional setup"
            "use async_startup for setup that requires database access, making a request or setting cookies"
        )
        assert cls.__init__ is Crawler.__init__, msg
        cls.NAME = cls.__name__.removesuffix("Crawler")
        cls.IS_GENERIC = is_generic
        cls.IS_FALLBACK_GENERIC = cls.NAME == "Generic"
        cls.IS_REAL_DEBRID = cls.NAME == "RealDebrid"
        cls.SUPPORTED_PATHS = _sort_supported_paths(cls.SUPPORTED_PATHS)
        cls.IS_ABC = is_abc

        if cls.IS_GENERIC:
            cls.GENERIC_NAME = generic_name or cls.NAME
            cls.SCRAPE_MAPPER_KEYS = ()
            cls.INFO = CrawlerInfo(cls.GENERIC_NAME, "::GENERIC CRAWLER::", (), cls.SUPPORTED_PATHS)  # type: ignore
            return

        if is_abc:
            return

        if not (cls.IS_FALLBACK_GENERIC or cls.IS_REAL_DEBRID):
            Crawler._assert_fields_overrides(cls, "PRIMARY_URL", "DOMAIN", "SUPPORTED_PATHS")

        if cls.OLD_DOMAINS:
            cls.REPLACE_OLD_DOMAINS_REGEX = re.compile("|".join(cls.OLD_DOMAINS))
            if not cls.SUPPORTED_DOMAINS:
                cls.SUPPORTED_DOMAINS = ()
            elif isinstance(cls.SUPPORTED_DOMAINS, str):
                cls.SUPPORTED_DOMAINS = (cls.SUPPORTED_DOMAINS,)
            cls.SUPPORTED_DOMAINS = tuple(sorted({*cls.OLD_DOMAINS, *cls.SUPPORTED_DOMAINS, cls.PRIMARY_URL.host}))
        else:
            cls.REPLACE_OLD_DOMAINS_REGEX = None
        _validate_supported_paths(cls)
        cls.SCRAPE_MAPPER_KEYS = _make_scrape_mapper_keys(cls)
        cls.FOLDER_DOMAIN = cls.FOLDER_DOMAIN or cls.DOMAIN.capitalize()
        wiki_supported_domains = _make_wiki_supported_domains(cls.SCRAPE_MAPPER_KEYS)
        cls.INFO = CrawlerInfo(cls.FOLDER_DOMAIN, cls.PRIMARY_URL, wiki_supported_domains, cls.SUPPORTED_PATHS)

    @abstractmethod
    async def fetch(self, scrape_item: ScrapeItem) -> None: ...

    @final
    @property
    def allow_no_extension(self) -> bool:
        return not self.manager.config_manager.settings_data.ignore_options.exclude_files_with_no_extension

    @property
    def deep_scrape(self) -> bool:
        return self.manager.config_manager.deep_scrape

    def _init_downloader(self) -> Downloader:
        self.downloader = dl = Downloader(self.manager, self.DOMAIN)
        dl.startup()
        return dl

    @final
    async def startup(self) -> None:
        """Starts the crawler."""
        async with self.startup_lock:
            if self.ready:
                return
            self.client = self.manager.client_manager.scraper_client
            self.manager.client_manager.rate_limits[self.DOMAIN] = self.RATE_LIMIT
            if self._DOWNLOAD_SLOTS:
                self.manager.client_manager.download_slots[self.DOMAIN] = self._DOWNLOAD_SLOTS
            self.downloader = self._init_downloader()
            self._register_response_checks()
            await self.async_startup()
            self.ready = True

    @final
    @contextlib.contextmanager
    def disable_on_error(self, msg: str) -> Generator[None]:
        try:
            yield
        except Exception:
            self.log(f"[{self.FOLDER_DOMAIN}] {msg}. Crawler has been disabled", 40)
            self.disabled = True
            raise

    async def async_startup(self) -> None: ...  # noqa: B027

    @final
    async def run(self, scrape_item: ScrapeItem) -> None:
        """Runs the crawler loop."""
        if not scrape_item.url.host:
            return
        if self.disabled:
            return

        self.waiting_items += 1
        async with self._semaphore:
            await self.manager.states.RUNNING.wait()
            self.waiting_items -= 1
            og_url = scrape_item.url
            scrape_item.url = url = self.transform_url(scrape_item.url)
            if og_url != url:
                log(f"URL transformation applied [{self.FOLDER_DOMAIN}]: \n  old_url: {og_url}\n  new_url: {url}")

            if url.path_qs in self.scraped_items:
                return log(f"Skipping {url} as it has already been scraped", 10)

            self.scraped_items.add(url.path_qs)
            async with self._fetch_context(scrape_item):
                self.pre_check_scrape_item(scrape_item)
                await self.fetch(scrape_item)

    def pre_check_scrape_item(self, scrape_item: ScrapeItem) -> None:
        if not self.SKIP_PRE_CHECK and scrape_item.url.path == "/":
            raise ValueError

    @classmethod
    def transform_url(cls, url: AbsoluteHttpURL) -> AbsoluteHttpURL:
        """Transforms an URL before it reaches the fetch method

        Override it to transform thumbnail URLs into full res URLs or URLs in an old unsupported format into a new one"""
        if cls.REPLACE_OLD_DOMAINS_REGEX is not None:
            new_host = cls.REPLACE_OLD_DOMAINS_REGEX.sub(cls.PRIMARY_URL.host, url.host)
            return url.with_host(new_host)
        return url

    @final
    @contextlib.asynccontextmanager
    async def _fetch_context(self, scrape_item: ScrapeItem) -> AsyncGenerator[TaskID]:
        with self.new_task_id(scrape_item.url) as task_id:
            try:
                yield task_id
            except ValueError:
                self.raise_exc(scrape_item, ScrapeError("Unknown URL path"))
            except MaxChildrenError as e:
                self.raise_exc(scrape_item, e)
            finally:
                pass

    @error_handling_wrapper
    def raise_exc(self, scrape_item: ScrapeItem, exc: type[Exception] | Exception | str) -> None:
        if isinstance(exc, str):
            exc = ScrapeError(exc)
        raise exc

    @final
    @contextlib.contextmanager
    def new_task_id(self, url: AbsoluteHttpURL) -> Generator[TaskID]:
        """Creates a new task_id (shows the URL in the UI and logs)"""
        scrape_prefix = "Scraping"
        if self.IS_FALLBACK_GENERIC:
            scrape_prefix += " (unsupported domain)"
        else:
            scrape_prefix += f" [{self.FOLDER_DOMAIN}]"
        log(f"{scrape_prefix}: {url}", 20)
        task_id = self.manager.progress_manager.scraping_progress.add_task(url)
        try:
            yield task_id
        finally:
            self.manager.progress_manager.scraping_progress.remove_task(task_id)

    @staticmethod
    def is_subdomain(url: AbsoluteHttpURL) -> bool:
        return url.host.removeprefix("www.").count(".") > 1

    @classmethod
    def is_self_subdomain(cls, url: AbsoluteHttpURL) -> bool:
        primary_domain = cls.PRIMARY_URL.host.removeprefix("www.")
        other_domain = url.host.removeprefix("www.")
        if primary_domain == other_domain:
            return False
        return primary_domain in other_domain and other_domain.count(".") > primary_domain.count(".")

    # TODO: make this sync
    async def handle_file(
        self,
        url: URL,
        scrape_item: ScrapeItem,
        filename: str,
        ext: str | None = None,
        *,
        custom_filename: str | None = None,
        debrid_link: URL | None = None,
        m3u8: m3u8.RenditionGroup | None = None,
    ) -> None:
        """Finishes handling the file and hands it off to the downloader."""
        if not ext:
            _, ext = filename.rsplit(".", 1)
        if custom_filename:
            original_filename, filename = filename, custom_filename
        elif self.DOMAIN in ["cyberdrop"]:
            original_filename, filename = remove_file_id(self.manager, filename, ext)
        else:
            original_filename = filename

        assert is_absolute_http_url(url)
        if isinstance(debrid_link, URL):
            assert is_absolute_http_url(debrid_link)
        download_folder = get_download_path(self.manager, scrape_item, self.FOLDER_DOMAIN)
        media_item = MediaItem.from_item(
            scrape_item, url, self.DOMAIN, download_folder, filename, original_filename, debrid_link, ext=ext
        )

        self.create_task(self.handle_media_item(media_item, m3u8))

    @final
    async def _download(self, media_item: MediaItem, m3u8: m3u8.RenditionGroup | None) -> None:
        try:
            if m3u8:
                await self.downloader.download_hls(media_item, m3u8)
            else:
                await self.downloader.run(media_item)

        finally:
            if self.manager.config_manager.settings_data.files.dump_json:
                data = [media_item.as_jsonable_dict()]
                await self.manager.log_manager.write_jsonl(data)

    async def check_complete(self, url: AbsoluteHttpURL, referer: AbsoluteHttpURL) -> bool:
        """Checks if this URL has been download before.

        This method is called automatically on a created media item,
        but Crawler code can use it to skip unnecessary requests"""
        check_complete = await self.manager.db_manager.history_table.check_complete(self.DOMAIN, url, referer)
        if check_complete:
            log(f"Skipping {url} as it has already been downloaded", 10)
            self.manager.progress_manager.download_progress.add_previously_completed()
        return check_complete

    async def handle_media_item(self, media_item: MediaItem, m3u8: m3u8.RenditionGroup | None = None) -> None:
        await self.manager.states.RUNNING.wait()
        if media_item.datetime and not isinstance(media_item.datetime, int):
            msg = f"Invalid datetime from '{self.FOLDER_DOMAIN}' crawler . Got {media_item.datetime!r}, expected int."
            log(msg, bug=True)

        check_complete = await self.check_complete(media_item.url, media_item.referer)
        if check_complete:
            if media_item.album_id:
                await self.manager.db_manager.history_table.set_album_id(self.DOMAIN, media_item)
            return

        if await self.check_skip_by_config(media_item):
            self.manager.progress_manager.download_progress.add_skipped()
            return

        self.create_task(self._download(media_item, m3u8))

    @final
    async def check_skip_by_config(self, media_item: MediaItem) -> bool:
        if (
            self.manager.config.download_options.skip_referer_seen_before
            and await self.manager.db_manager.temp_referer_table.check_referer(media_item.referer)
        ):
            log(f"Download skip {media_item.url} as referer has been seen before", 10)
            return True

        assert media_item.url.host
        media_host = media_item.url.host

        if (hosts := self.manager.config.ignore_options.skip_hosts) and any(host in media_host for host in hosts):
            log(f"Download skip {media_item.url} due to skip_hosts config", 10)
            return True

        if (hosts := self.manager.config.ignore_options.only_hosts) and not any(host in media_host for host in hosts):
            log(f"Download skip {media_item.url} due to only_hosts config", 10)
            return True

        if (regex := self.manager.config.ignore_options.filename_regex_filter) and re.search(
            regex, media_item.filename
        ):
            log(f"Download skip {media_item.url} due to filename regex filter config", 10)
            return True

        return False

    @final
    async def check_complete_from_referer(
        self: Crawler, scrape_item: ScrapeItem | URL, any_crawler: bool = False
    ) -> bool:
        """Checks if the scrape item has already been scraped.

        if `any_crawler` is `True`, checks database entries for all crawlers and returns `True` if at least 1 of them has marked it as completed
        """
        url = scrape_item if isinstance(scrape_item, URL) else scrape_item.url
        domain = None if any_crawler else self.DOMAIN
        downloaded = await self.manager.db_manager.history_table.check_complete_by_referer(domain, url)
        if downloaded:
            log(f"Skipping {url} as it has already been downloaded", 10)
            self.manager.progress_manager.download_progress.add_previously_completed()
            return True
        return False

    @final
    async def check_complete_by_hash(
        self: Crawler, scrape_item: ScrapeItem | URL, hash_type: str, hash_value: str
    ) -> bool:
        """Returns `True` if at least 1 file with this hash is recorded on the database"""
        downloaded = await self.manager.db_manager.hash_table.check_hash_exists(hash_type, hash_value)
        if downloaded:
            url = scrape_item if isinstance(scrape_item, URL) else scrape_item.url
            log(f"Skipping {url} as its hash ({hash_type}:{hash_value}) has already been downloaded", 10)
            self.manager.progress_manager.download_progress.add_previously_completed()
            return True
        return False

    async def get_album_results(self, album_id: str) -> dict[str, int]:
        """Checks whether an album has completed given its domain and album id."""
        return await self.manager.db_manager.history_table.check_album(self.DOMAIN, album_id)

    def handle_external_links(self, scrape_item: ScrapeItem) -> None:
        """Maps external links to the scraper class."""
        scrape_item.reset()
        self.create_task(self.manager.scrape_mapper.filter_and_send_to_crawler(scrape_item))

    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    def get_filename_and_ext(
        self, filename: str, forum: bool = False, assume_ext: str | None = None
    ) -> tuple[str, str]:
        """Wrapper around `utils.get_filename_and_ext`.
        Calls it as is.
        If that fails, appends `assume_ext` and tries again, but only if the user had exclude_files_with_no_extension = `False`
        """
        try:
            return get_filename_and_ext(filename, forum)
        except NoExtensionError:
            if assume_ext and self.allow_no_extension:
                return get_filename_and_ext(filename + assume_ext, forum)
            raise

    def check_album_results(self, url: URL, album_results: dict[str, Any]) -> bool:
        """Checks whether an album has completed given its domain and album id."""
        if not album_results:
            return False
        url_path = MediaItem.create_db_path(url, self.DOMAIN)
        if url_path in album_results and album_results[url_path] != 0:
            log(f"Skipping {url} as it has already been downloaded")
            self.manager.progress_manager.download_progress.add_previously_completed()
            return True
        return False

    def create_title(self, title: str, album_id: str | None = None, thread_id: int | None = None) -> str:
        """Creates the title for the scrape item."""
        if not title:
            title = "Untitled"

        title = title.strip()
        if album_id and self.manager.config.download_options.include_album_id_in_folder_name:
            title = f"{title} {album_id}"

        if thread_id and self.manager.config.download_options.include_thread_id_in_folder_name:
            title = f"{title} {thread_id}"

        if not self.manager.config.download_options.remove_domains_from_folder_names:
            title = f"{title} ({self.FOLDER_DOMAIN})"

        # Remove double spaces
        while True:
            title = title.replace("  ", " ")
            if "  " not in title:
                break
        return title

    @property
    def separate_posts(self) -> bool:
        return self.manager.config.download_options.separate_posts

    def create_separate_post_title(
        self,
        title: str | None = None,
        id: str | None = None,
        date: datetime.datetime | datetime.date | int | None = None,
        /,
    ) -> str:
        if not self.separate_posts:
            return ""
        title_format = self.manager.config.download_options.separate_posts_format
        if title_format.strip().casefold() == "{default}":
            title_format = self.DEFAULT_POST_TITLE_FORMAT
        if isinstance(date, int):
            date = datetime.datetime.fromtimestamp(date)

        post_title, _ = safe_format(title_format, id=id, number=id, date=date, title=title)
        return post_title

    def parse_url(self, link_str: str, relative_to: URL | None = None, *, trim: bool | None = None) -> AbsoluteHttpURL:
        """Wrapper around `utils.parse_url` to use `self.PRIMARY_URL` as base"""
        base = relative_to or self.PRIMARY_URL
        assert is_absolute_http_url(base)
        if trim is None:
            trim = self.DEFAULT_TRIM_URLS
        return parse_url(link_str, base, trim=trim)

    def update_cookies(self, cookies: dict, url: URL | None = None) -> None:
        """Update cookies for the provided URL

        If `url` is `None`, defaults to `self.PRIMARY_URL`
        """
        response_url = url or self.PRIMARY_URL
        self.client.client_manager.cookies.update_cookies(cookies, response_url)

    def iter_tags(
        self,
        soup: Tag,
        selector: str,
        /,
        attribute: str = "href",
        *,
        results: dict[str, int] | None = None,
    ) -> Generator[tuple[AbsoluteHttpURL | None, AbsoluteHttpURL]]:
        """Generates tuples with an URL from the `src` value of the first image tag (AKA the thumbnail) and an URL from the value of `attribute`

        :param results: must be the output of `self.get_album_results`.
        If provided, it will be used as a filter, to only yield items that has not been downloaded before"""
        album_results = results or {}

        for tag in css.iselect(soup, selector):
            link_str: str | None = css.get_attr_or_none(tag, attribute)
            if not link_str:
                continue
            link = self.parse_url(link_str)
            if self.check_album_results(link, album_results):
                continue
            if t_tag := tag.select_one("img"):
                thumb_str: str | None = css.get_attr_or_none(t_tag, "src")
            else:
                thumb_str = None
            thumb = self.parse_url(thumb_str) if thumb_str and not is_blob_or_svg(thumb_str) else None
            yield thumb, link

    def iter_children(
        self,
        scrape_item: ScrapeItem,
        soup: BeautifulSoup,
        selector: str,
        /,
        attribute: str = "href",
        *,
        results: dict[str, int] | None = None,
        **kwargs: Any,
    ) -> Generator[tuple[AbsoluteHttpURL | None, ScrapeItem]]:
        """Generates tuples with an URL from the `src` value of the first image tag (AKA the thumbnail) and a new scrape item from the value of `attribute`

        :param results: must be the output of `self.get_album_results`.
        If provided, it will be used as a filter, to only yield items that has not been downloaded before
        :param **kwargs: Will be forwarded to `scrape.item.create_child`"""
        for thumb, link in self.iter_tags(soup, selector, attribute, results=results):
            new_scrape_item = scrape_item.create_child(link, **kwargs)
            yield thumb, new_scrape_item
            scrape_item.add_children()

    async def web_pager(
        self, url: AbsoluteHttpURL, next_page_selector: str | None = None, *, cffi: bool = False, **kwargs: Any
    ) -> AsyncGenerator[BeautifulSoup]:
        """Generator of website pages.

        :param next_page_selector: If `None`, `self.next_page_selector` will be used
        :param cffi: If `True`, uses `curl_cffi` to get the soup for each page. Otherwise, `aiohttp` will be used
        :param **kwargs: Will be forwarded to `self.parse_url` to parse each new page"""

        async for soup in self._web_pager(url, next_page_selector, cffi=cffi, **kwargs):
            yield soup

    async def _web_pager(
        self,
        url: AbsoluteHttpURL,
        selector: Callable[[BeautifulSoup], str | None] | str | None = None,
        *,
        cffi: bool = False,
        **kwargs: Any,
    ) -> AsyncGenerator[BeautifulSoup]:
        """Generator of website pages.

        :param next_page_selector: If `None`, `self.next_page_selector` will be used
        :param cffi: If `True`, uses `curl_cffi` to get the soup for each page. Otherwise, `aiohttp` will be used
        :param **kwargs: Will be forwarded to `self.parse_url` to parse each new page"""

        page_url = url
        if callable(selector):
            get_next_page = selector
        else:
            selector = selector or self.NEXT_PAGE_SELECTOR
            assert selector, f"No selector was provided and {self.DOMAIN} does define a next_page_selector"
            func = css.select_one_get_attr_or_none
            get_next_page = partial(func, selector=selector, attribute="href")

        while True:
            soup = await self.request_soup(page_url, impersonate=cffi or None)
            yield soup
            page_url_str = get_next_page(soup)
            if not page_url_str:
                break
            page_url = self.parse_url(page_url_str, **kwargs)

    @error_handling_wrapper
    async def direct_file(self, scrape_item: ScrapeItem, url: URL | None = None, assume_ext: str | None = None) -> None:
        """Download a direct link file. Filename will be the url slug"""
        link = url or scrape_item.url
        filename, ext = self.get_filename_and_ext(link.name or link.parent.name, assume_ext=assume_ext)
        await self.handle_file(link, scrape_item, filename, ext)

    @final
    def parse_date(self, date_or_datetime: str, format: str | None = None, /) -> TimeStamp | None:
        if parsed_date := self._parse_date(date_or_datetime, format):
            return to_timestamp(parsed_date)

    @final
    def parse_iso_date(self, date_or_datetime: str, /) -> TimeStamp | None:
        if parsed_date := self._parse_date(date_or_datetime, None, iso=True):
            return to_timestamp(parsed_date)

    @final
    def _parse_date(
        self, date_or_datetime: str, format: str | None = None, /, *, iso: bool = False
    ) -> datetime.datetime | None:
        assert not (iso and format), "Only `format` or `iso` can be used, not both"
        msg = f"Date parsing for {self.DOMAIN} seems to be broken"
        if not date_or_datetime:
            log(f"{msg}: Unable to extract date", bug=True)
            return
        if format:
            assert not (format == "%Y-%m-%d" or format.startswith("%Y-%m-%d %H:%M:%S")), (
                f"{msg} Do not use a custom format to parse iso8601 dates. Call parse_iso_date instead"
            )
        try:
            with warnings.catch_warnings(action="error"):
                if iso:
                    parsed_date = datetime.datetime.fromisoformat(date_or_datetime)
                elif format:
                    parsed_date = datetime.datetime.strptime(date_or_datetime, format)
                else:
                    parsed_date = parse_human_date(date_or_datetime)

            if parsed_date:
                return parsed_date

        except Exception as e:
            msg = f"{msg}. {date_or_datetime = }{format = }: {e!r}"

        log(msg, bug=True)

    async def _get_redirect_url(self, url: AbsoluteHttpURL) -> AbsoluteHttpURL:
        async with self.request(url) as resp:
            return resp.url

    @final
    @error_handling_wrapper
    async def follow_redirect(self, scrape_item: ScrapeItem) -> None:
        redirect = await self._get_redirect_url(scrape_item.url)
        if scrape_item.url == redirect:
            raise ScrapeError(422, "Infinite redirect")
        scrape_item.url = redirect
        self.create_task(self.run(scrape_item))

    @staticmethod
    def register_cache_filter(
        url: URL, filter_fn: Callable[[AnyResponse], bool] | Callable[[AnyResponse], Awaitable[bool]]
    ) -> None:
        filters.cache_filter_functions[url.host] = filter_fn

    async def get_m3u8_from_playlist_url(
        self,
        m3u8_playlist_url: AbsoluteHttpURL,
        /,
        headers: dict[str, str] | None = None,
        *,
        only: Iterable[str] = (),
        exclude: Iterable[str] = ("vp09",),
    ) -> tuple[m3u8.RenditionGroup, m3u8.RenditionGroupDetails]:
        """Get m3u8 rendition group from a playlist m3u8 (variant m3u8), selecting the best format"""
        m3u8_playlist = await self._get_m3u8(m3u8_playlist_url, headers)
        rendition_group_info = m3u8.get_best_group_from_playlist(m3u8_playlist, only=only, exclude=exclude)
        renditions_urls = rendition_group_info.urls
        video = await self._get_m3u8(renditions_urls.video, headers, "video")
        audio = await self._get_m3u8(renditions_urls.audio, headers, "audio") if renditions_urls.audio else None
        subtitle = (
            await self._get_m3u8(renditions_urls.subtitle, headers, "subtitles") if renditions_urls.subtitle else None
        )
        return m3u8.RenditionGroup(video, audio, subtitle), rendition_group_info

    async def get_m3u8_from_index_url(
        self, url: AbsoluteHttpURL, /, headers: dict[str, str] | None = None
    ) -> m3u8.RenditionGroup:
        """Get m3u8 rendition group from an index that only has 1 rendition, a video (non variant m3u8)"""
        return m3u8.RenditionGroup(await self._get_m3u8(url, headers, "video"))

    async def _get_m3u8(
        self,
        url: AbsoluteHttpURL,
        /,
        headers: dict[str, str] | None = None,
        media_type: Literal["video", "audio", "subtitles"] | None = None,
    ) -> m3u8.M3U8:
        content = await self.request_text(url, headers=headers)
        return m3u8.M3U8(content, url.parent, media_type)

    def create_custom_filename(
        self,
        name: str,
        ext: str,
        /,
        *,
        file_id: str | None = None,
        video_codec: str | None = None,
        audio_codec: str | None = None,
        resolution: Resolution | str | int | None = None,
        hash_string: str | None = None,
        only_truncate_stem: bool = True,
    ) -> str:
        calling_args = {name: value for name, value in locals().items() if value is not None and name not in ("self",)}
        # remove OS separators (if any)
        stem = sanitize_filename(Path(name).as_posix().replace("/", "-")).strip()
        extra_info: list[str] = []

        if _placeholder_config.include_file_id and file_id:
            extra_info.append(file_id)
        if _placeholder_config.include_video_codec and video_codec:
            extra_info.append(video_codec)
        if _placeholder_config.include_audio_codec and audio_codec:
            extra_info.append(audio_codec)

        if (
            _placeholder_config.include_resolution
            and resolution
            and resolution not in [Resolution.highest(), Resolution.unknown()]
        ):
            if not isinstance(resolution, Resolution):
                resolution = Resolution.parse(resolution)
            extra_info.append(resolution.name)

        if _placeholder_config.include_hash and hash_string:
            assert any(hash_string.startswith(x) for x in HASH_PREFIXES), f"Invalid: {hash_string = }"
            extra_info.append(hash_string)

        filename, extra_info_had_invalid_chars = _make_custom_filename(stem, ext, extra_info, only_truncate_stem)
        if extra_info_had_invalid_chars:
            msg = (
                f"Custom filename creation for {self.FOLDER_DOMAIN} seems to be broken. "
                f"Important information was removed while creating a filename. "
                f"\n{calling_args}"
            )
            log(msg, bug=True)
        return filename

    @final
    def get_cookies(self, partial_match_domain: bool = False) -> Iterable[tuple[str, BaseCookie[str]]]:
        if partial_match_domain:
            yield from self.client.client_manager.filter_cookies_by_word_in_domain(self.DOMAIN)
        else:
            yield str(self.PRIMARY_URL.host), self.client.client_manager.cookies.filter_cookies(self.PRIMARY_URL)

    @final
    def get_cookie_value(self, cookie_name: str, partial_match_domain: bool = False) -> str | None:
        def get_morsels_by_name():
            for _, cookie in self.get_cookies(partial_match_domain):
                if morsel := cookie.get(cookie_name):
                    yield morsel

        if newest := max(get_morsels_by_name(), key=lambda x: int(x["max-age"] or 0), default=None):
            return newest.value


def _make_scrape_mapper_keys(cls: type[Crawler] | Crawler) -> tuple[str, ...]:
    if cls.SUPPORTED_DOMAINS:
        hosts = cls.SUPPORTED_DOMAINS
    else:
        hosts = cls.DOMAIN
    if isinstance(hosts, str):
        hosts = (hosts,)
    return tuple(sorted({host.removeprefix("www.") for host in hosts}))


def _make_custom_filename(stem: str, ext: str, extra_info: list[str], only_truncate_stem: bool) -> tuple[str, bool]:
    truncate_len = constants.MAX_NAME_LENGTHS["FILE"] - len(ext)
    invalid_extra_info_chars = False
    if extra_info:
        extra_info_str = "".join(f"[{info}]" for info in extra_info)
        clean_extra_info_str = sanitize_filename(extra_info_str)
        invalid_extra_info_chars = clean_extra_info_str != extra_info_str
        if only_truncate_stem and (new_truncate_len := truncate_len - len(clean_extra_info_str) - 1) > 0:
            truncated_stem = f"{truncate_str(stem, new_truncate_len)} {clean_extra_info_str}"
        else:
            truncated_stem = truncate_str(f"{stem} {clean_extra_info_str}", truncate_len)

    else:
        truncated_stem = truncate_str(stem, truncate_len)

    return f"{truncated_stem}{ext}", invalid_extra_info_chars


class Site(NamedTuple):
    PRIMARY_URL: AbsoluteHttpURL
    DOMAIN: str
    SUPPORTED_DOMAINS: SupportedDomains = ()
    FOLDER_DOMAIN: str = ""


_CrawlerT = TypeVar("_CrawlerT", bound=Crawler)


def create_crawlers(urls: Iterable[str] | Iterable[yarl.URL], base_crawler: type[_CrawlerT]) -> set[type[_CrawlerT]]:
    """Creates new subclasses of the base crawler from the urls"""
    return {_create_subclass(url, base_crawler) for url in urls}


def _create_subclass(url: yarl.URL | str, base_class: type[_CrawlerT]) -> type[_CrawlerT]:
    if isinstance(url, str):
        url = AbsoluteHttpURL(url)
    assert is_absolute_http_url(url)
    primary_url = remove_trailing_slash(url)
    domain = primary_url.host.removeprefix("www.")
    class_name = _make_crawler_name(domain)
    class_attributes = Site(primary_url, domain)._asdict()
    return type(class_name, (base_class,), class_attributes)  # type: ignore


def _make_crawler_name(input_string: str) -> str:
    clean_string = re.sub(r"[^a-zA-Z0-9]+", " ", input_string).strip()
    cap_name = clean_string.title().replace(" ", "")
    assert cap_name and cap_name.isalnum(), (
        f"Can not generate a valid class name from {input_string}. Needs to be defined as a concrete class"
    )
    if cap_name[0].isdigit():
        cap_name = "_" + cap_name
    return f"{cap_name}Crawler"


def _validate_supported_paths(cls: type[Crawler]) -> None:
    for path_name, paths in cls.SUPPORTED_PATHS.items():
        assert path_name, f"{cls.__name__}, Invalid path: {path_name}"
        assert isinstance(paths, str | tuple), f"{cls.__name__}, Invalid path {path_name}: {type(paths)}"
        if path_name != "Direct links":
            assert paths, f"{cls.__name__} has not paths for {path_name}"

        if path_name.startswith("*"):  # note
            return
        if isinstance(paths, str):
            paths = (paths,)
        for path in paths:
            assert "`" not in path, f"{cls.__name__}, Invalid path {path_name}: {path}"


def _make_wiki_supported_domains(scrape_mapper_keys: tuple[str, ...]) -> tuple[str, ...]:
    def generalize(domain):
        if "." not in domain:
            return f"{domain}.*"
        return domain

    return tuple(sorted(generalize(domain) for domain in scrape_mapper_keys))


def _sort_supported_paths(supported_paths: SupportedPaths) -> dict[str, OneOrTuple[str]]:
    def try_sort(value: OneOrTuple[str]) -> OneOrTuple[str]:
        if isinstance(value, tuple):
            return tuple(sorted(value))
        return value

    path_pairs = ((key, try_sort(value)) for key, value in supported_paths.items())
    return dict(sorted(path_pairs, key=lambda x: x[0].casefold()))


def auto_task_id(
    func: Callable[Concatenate[_CrawlerT, ScrapeItem, P], R | Coroutine[None, None, R]],
) -> Callable[Concatenate[_CrawlerT, ScrapeItem, P], Coroutine[None, None, R]]:
    """Autocreate a new `task_id` from the scrape_item of the method"""

    @wraps(func)
    async def wrapper(self: _CrawlerT, scrape_item: ScrapeItem, *args: P.args, **kwargs: P.kwargs) -> R:
        await self.manager.states.RUNNING.wait()
        with self.new_task_id(scrape_item.url):
            result = func(self, scrape_item, *args, **kwargs)
            if inspect.isawaitable(result):
                return await result
            return result

    return wrapper
