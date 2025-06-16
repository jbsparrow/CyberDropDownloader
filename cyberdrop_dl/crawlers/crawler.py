from __future__ import annotations

import asyncio
import re
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from functools import partial, wraps
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, NamedTuple, ParamSpec, TypeAlias, TypeVar, final

from aiolimiter import AsyncLimiter
from yarl import URL

from cyberdrop_dl import constants
from cyberdrop_dl.constants import NEW_ISSUE_URL
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL, MediaItem, ScrapeItem
from cyberdrop_dl.downloader.downloader import Downloader
from cyberdrop_dl.scraper import filters
from cyberdrop_dl.utils import css
from cyberdrop_dl.utils.database.tables.history_table import get_db_path
from cyberdrop_dl.utils.dates import TimeStamp, parse_date, to_timestamp
from cyberdrop_dl.utils.logger import log, log_debug
from cyberdrop_dl.utils.m3u8 import M3U8, M3U8Media, RenditionGroup
from cyberdrop_dl.utils.utilities import (
    error_handling_wrapper,
    get_download_path,
    get_filename_and_ext,
    is_absolute_http_url,
    parse_url,
    remove_file_id,
    sanitize_filename,
    sort_dict,
    truncate_str,
)

P = ParamSpec("P")
R = TypeVar("R")
T = TypeVar("T")


if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Awaitable, Callable, Coroutine, Generator

    from aiohttp_client_cache.response import AnyResponse
    from bs4 import BeautifulSoup, Tag

    from cyberdrop_dl.clients.scraper_client import ScraperClient
    from cyberdrop_dl.managers.manager import Manager


OneOrTuple: TypeAlias = T | tuple[T, ...]
SupportedPaths: TypeAlias = Mapping[str, OneOrTuple[str]]
SupportedDomains: TypeAlias = OneOrTuple[str]

UNKNOWN_URL_PATH_MSG = "Unknown URL path"
HASH_PREFIXES = "md5:", "sha1:", "sha256:", "xxh128:"
VALID_RESOLUTION_NAMES = "4K", "8K", "Unknown"


@dataclass(slots=True, frozen=True)
class PlaceHolderConfig:
    file_id: bool = True
    video_codec: bool = True
    audio_codec: bool = True
    resolution: bool = True
    hash: bool = True


class CrawlerInfo(NamedTuple):
    site: str
    primary_url: URL
    supported_domains: tuple[str, ...]
    supported_paths: SupportedPaths


def create_task_id(func: Callable[P, Coroutine[None, None, R]]) -> Callable[P, Coroutine[None, None, R | None]]:
    """Wrapper that handles `task_id` creation and removal for scrape items"""

    @wraps(func)
    async def wrapper(*args, **kwargs) -> R | None:
        self: Crawler = args[0]
        scrape_item: ScrapeItem = args[1]
        await self.manager.states.RUNNING.wait()
        task_id = self.scraping_progress.add_task(scrape_item.url)
        try:
            if not self.SKIP_PRE_CHECK:
                pre_check_scrape_item(scrape_item)
            return await func(scrape_item, **kwargs)
        except ValueError:
            log(f"Scrape Failed: {UNKNOWN_URL_PATH_MSG}: {scrape_item.url}", 40)
            self.manager.progress_manager.scrape_stats_progress.add_failure(UNKNOWN_URL_PATH_MSG)
            await self.manager.log_manager.write_scrape_error_log(scrape_item.url, UNKNOWN_URL_PATH_MSG)
        finally:
            self.scraping_progress.remove_task(task_id)

    return wrapper


class Crawler(ABC):
    SUPPORTED_DOMAINS: ClassVar[SupportedDomains] = ()
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {}
    DEFAULT_POST_TITLE_FORMAT: ClassVar[str] = "{date} - {number} - {title}"

    UPDATE_UNSUPPORTED: ClassVar[bool] = False
    SKIP_PRE_CHECK: ClassVar[bool] = False
    NEXT_PAGE_SELECTOR: ClassVar[str] = ""

    PRIMARY_URL: ClassVar[AbsoluteHttpURL]
    DOMAIN: ClassVar[str]
    FOLDER_DOMAIN: ClassVar[str] = ""

    @final
    def __init__(self, manager: Manager) -> None:
        self.manager = manager
        self.downloader: Downloader = field(init=False)
        self.scraping_progress = manager.progress_manager.scraping_progress
        self.client: ScraperClient = field(init=False)
        self.startup_lock = asyncio.Lock()
        self.request_limiter = AsyncLimiter(10, 1)
        self.ready: bool = False
        self.logged_in: bool = False
        self.scraped_items: list[str] = []
        self.waiting_items = 0
        self.log = log
        self.log_debug = log_debug
        self._semaphore = asyncio.Semaphore(20)
        self.__post_init__()

    def __post_init__(self) -> None: ...  # noqa: B027

    def __init_subclass__(cls, is_abc: bool = False, **kwargs) -> None:
        super().__init_subclass__(**kwargs)

        msg = (
            f"Subclass {cls.__name__} must not override __init__ method,",
            "use __post_init__ for additional setup",
            "use async_startup for setup that requires database access, making a request or setting cookies",
        )
        assert cls.__init__ is Crawler.__init__, msg
        if is_abc:
            return

        if cls.DOMAIN != "generic":
            REQUIRED_FIELDS = "PRIMARY_URL", "DOMAIN", "SUPPORTED_PATHS"
            for field_name in REQUIRED_FIELDS:
                assert getattr(cls, field_name, None), f"Subclass {cls.__name__} must override: {field_name}"

        cls.FOLDER_DOMAIN = cls.FOLDER_DOMAIN or cls.DOMAIN.capitalize()
        cls.NAME = cls.__name__.removesuffix("Crawler")
        cls.SCRAPE_MAPPER_KEYS = make_scrape_mapper_keys(cls)
        cls.SUPPORTED_PATHS = sort_dict(cls.SUPPORTED_PATHS)
        cls.INFO = CrawlerInfo(cls.FOLDER_DOMAIN, cls.PRIMARY_URL, cls.SCRAPE_MAPPER_KEYS, cls.SUPPORTED_PATHS)

        for path_name, paths in cls.SUPPORTED_PATHS.items():
            assert path_name, f"{cls.__name__}, Invalid path: {path_name}"
            assert isinstance(paths, str | tuple), f"{cls.__name__}, Invalid path {path_name}: {type(paths)}"
            if path_name != "Direct links":
                assert paths, f"{cls.__name__} has not paths for {path_name}"

            if isinstance(paths, str):
                paths = (paths,)
            for path in paths:
                assert "`" not in path, f"{cls.__name__}, Invalid path {path_name}: {path}"

    @abstractmethod
    async def fetch(self, scrape_item: ScrapeItem) -> None: ...

    @final
    @property
    def allow_no_extension(self) -> bool:
        return not self.manager.config_manager.settings_data.ignore_options.exclude_files_with_no_extension

    @final
    async def startup(self) -> None:
        """Starts the crawler."""
        async with self.startup_lock:
            if self.ready:
                return
            self.client = self.manager.client_manager.scraper_session
            self.downloader = Downloader(self.manager, self.DOMAIN)
            self.downloader.startup()
            await self.async_startup()
            self.ready = True

    async def async_startup(self) -> None: ...  # noqa: B027

    @final
    async def run(self, item: ScrapeItem) -> None:
        """Runs the crawler loop."""
        if not item.url.host:
            return

        await self.manager.states.RUNNING.wait()
        self.waiting_items += 1
        scrape_prefix = "Scraping"
        if self.DOMAIN == "generic":
            scrape_prefix += " (unsupported domain)"

        async with self._semaphore:
            self.waiting_items -= 1
            if item.url.path_qs not in self.scraped_items:
                log(f"{scrape_prefix}: {item.url}", 20)
                self.scraped_items.append(item.url.path_qs)
                await create_task_id(self.fetch)(self, item)
            else:
                log(f"Skipping {item.url} as it has already been scraped", 10)

    async def handle_file(
        self,
        url: URL,
        scrape_item: ScrapeItem,
        filename: str,
        ext: str,
        *,
        custom_filename: str | None = None,
        debrid_link: URL | None = None,
        m3u8_media: M3U8Media | None = None,
    ) -> None:
        """Finishes handling the file and hands it off to the downloader."""

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
        media_item = MediaItem(url, scrape_item, download_folder, filename, original_filename, debrid_link, ext=ext)
        await self.handle_media_item(media_item, m3u8_media)

    async def handle_media_item(self, media_item: MediaItem, m3u8_media: M3U8Media | None = None) -> None:
        await self.manager.states.RUNNING.wait()
        if media_item.datetime and not isinstance(media_item.datetime, int):
            msg = f"Invalid datetime from '{self.FOLDER_DOMAIN}' crawler . Got {media_item.datetime!r}, expected int. "
            msg += f"Please file a bug report at {NEW_ISSUE_URL}"
            log(msg, 30)

        check_complete = await self.manager.db_manager.history_table.check_complete(
            self.DOMAIN, media_item.url, media_item.referer
        )
        if check_complete:
            if media_item.album_id:
                await self.manager.db_manager.history_table.set_album_id(self.DOMAIN, media_item)
            log(f"Skipping {media_item.url} as it has already been downloaded", 10)
            self.manager.progress_manager.download_progress.add_previously_completed()
            return

        if await self.check_skip_by_config(media_item):
            self.manager.progress_manager.download_progress.add_skipped()
            return

        if not m3u8_media:
            self.manager.task_group.create_task(self.downloader.run(media_item))
            return

        self.manager.task_group.create_task(self.downloader.download_hls(media_item, m3u8_media))

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

    async def check_complete_from_referer(self, scrape_item: ScrapeItem | URL) -> bool:
        """Checks if the scrape item has already been scraped."""
        url = scrape_item if isinstance(scrape_item, URL) else scrape_item.url
        downloaded = await self.manager.db_manager.history_table.check_complete_by_referer(self.DOMAIN, url)
        if downloaded:
            log(f"Skipping {url} as it has already been downloaded", 10)
            self.manager.progress_manager.download_progress.add_previously_completed()
            return True
        return False

    async def get_album_results(self, album_id: str) -> dict[str, int]:
        """Checks whether an album has completed given its domain and album id."""
        return await self.manager.db_manager.history_table.check_album(self.DOMAIN, album_id)

    def handle_external_links(self, scrape_item: ScrapeItem, reset: bool = False) -> None:
        """Maps external links to the scraper class."""
        if reset:
            scrape_item.reset()
        self.manager.task_group.create_task(self.manager.scrape_mapper.filter_and_send_to_crawler(scrape_item))

    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    def get_filename_and_ext(self, filename: str, *args, assume_ext: str | None = None, **kwargs):
        """Wrapper around `utils.get_filename_and_ext`.

        If `ignore_options.exclude_files_with_no_extension` is `True`, `assume_ext` is not None and the file has no extension,
        The value of `assume_ext` will be used as `ext`

        In any other case, it will just call `utils.get_filename_and_ext`
        """
        filename_as_path = Path(filename)
        if assume_ext and self.allow_no_extension and not filename_as_path.suffix:
            filename_as_path = filename_as_path.with_suffix(assume_ext)
            new_filename, ext = get_filename_and_ext(str(filename_as_path), *args, *kwargs)
            return Path(new_filename).stem, ext
        return get_filename_and_ext(filename, *args, *kwargs)

    def check_album_results(self, url: URL, album_results: dict[str, Any]) -> bool:
        """Checks whether an album has completed given its domain and album id."""
        if not album_results:
            return False
        url_path = get_db_path(url, self.DOMAIN)
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

    def create_separate_post_title(
        self,
        title: str | None = None,
        id: str | None = None,
        date: datetime | int | None = None,
        /,
    ) -> str:
        if not self.manager.config.download_options.separate_posts:
            return ""
        title_format = self.manager.config.download_options.separate_posts_format
        if title_format.strip().casefold() == "{default}":
            title_format = self.DEFAULT_POST_TITLE_FORMAT
        if isinstance(date, int):
            date = datetime.fromtimestamp(date)
        if isinstance(date, datetime):
            date_str = date.isoformat()
        else:
            date_str: str | None = date

        def default_if_none(value: str | None, default: str) -> str:
            return default if value is None else value

        id = default_if_none(id, "Unknown")
        title = default_if_none(title, "Untitled")
        date_str = default_if_none(date_str, "NO_DATE")
        return title_format.format(id=id, date=date_str, title=title)

    def parse_url(self, link_str: str, relative_to: URL | None = None, *, trim: bool = True) -> AbsoluteHttpURL:
        """Wrapper arround `utils.parse_url` to use `self.PRIMARY_URL` as base"""
        base = relative_to or self.PRIMARY_URL
        assert is_absolute_http_url(base)
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

        def is_embedded_image(link: str) -> bool:
            """Checks if the link is an embedded image URL."""
            return link.startswith("data:image") or link.startswith("blob:")

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
            thumb = self.parse_url(thumb_str) if thumb_str and not is_embedded_image(thumb_str) else None
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
        self, url: URL, next_page_selector: str | None = None, *, cffi: bool = False, **kwargs: Any
    ) -> AsyncGenerator[BeautifulSoup]:
        """Generator of website pages.

        :param next_page_selector: If `None`, `self.next_page_selector` will be used
        :param cffi: If `True`, uses `curl_cffi` to get the soup for each page. Otherwise, `aiohttp` will be used
        :param **kwargs: Will be forwarded to `self.parse_url` to parse each new page"""

        async for soup in self._web_pager(url, next_page_selector, cffi=cffi, **kwargs):
            yield soup

    async def _web_pager(
        self,
        url: URL,
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

        get_soup = self.client.get_soup_cffi if cffi else self.client.get_soup
        while True:
            async with self.request_limiter:
                soup = await get_soup(self.DOMAIN, page_url)
            yield soup
            page_url_str = get_next_page(soup)
            if not page_url_str:
                break
            page_url = self.parse_url(page_url_str, **kwargs)

    @error_handling_wrapper
    async def direct_file(self, scrape_item: ScrapeItem, url: URL | None = None, assume_ext: str | None = None) -> None:
        """Download a direct link file. Filename will be extrcation for the url"""
        link = url or scrape_item.url
        filename, ext = self.get_filename_and_ext(link.name, assume_ext=assume_ext)
        await self.handle_file(link, scrape_item, filename, ext)

    def parse_date(self, date_or_datetime: str, format: str | None = None, /) -> TimeStamp | None:
        if parsed_date := self._parse_date(date_or_datetime, format):
            return to_timestamp(parsed_date)

    def _parse_date(self, date_or_datetime: str, format: str | None = None, /) -> datetime | None:
        msg = f"Date parsing for {self.DOMAIN} seems to be broken. Please report this as a bug at {NEW_ISSUE_URL}"
        if not date_or_datetime:
            log(f"{msg}: Unable to extract date from soup", 30)
            return None
        try:
            if format:
                parsed_date = datetime.strptime(date_or_datetime, format)
            else:
                parsed_date = parse_date(date_or_datetime)
        except (ValueError, TypeError) as e:
            msg = f"{msg}: {e}"

        else:
            return parsed_date

        log(msg, 30)

    @staticmethod
    def register_cache_filter(
        url: URL, filter_fn: Callable[[AnyResponse], bool] | Callable[[AnyResponse], Awaitable[bool]]
    ) -> None:
        filters.cache_filter_functions[url.host] = filter_fn

    async def get_m3u8_playlist(self, m3u8_playlist_url: AbsoluteHttpURL, /) -> tuple[M3U8Media, RenditionGroup]:
        m3u8_playlist = await self._get_m3u8(m3u8_playlist_url)
        assert m3u8_playlist.is_variant
        rendition_group = m3u8_playlist.as_variant().get_best_group(exclude="vp09")
        video = await self._get_m3u8(rendition_group.urls.video)
        audio = await self._get_m3u8(rendition_group.urls.audio) if rendition_group.urls.audio else None
        subtitle = await self._get_m3u8(rendition_group.urls.subtitle) if rendition_group.urls.subtitle else None
        return M3U8Media(video, audio, subtitle), rendition_group

    async def _get_m3u8(self, url: AbsoluteHttpURL, headers: dict[str, str] | None = None) -> M3U8:
        headers = headers or {}
        async with self.request_limiter:
            content = await self.client.get_text(self.DOMAIN, url, headers)
        return M3U8(content, url.parent)

    def create_custom_filename(
        self,
        name: str,
        ext: str,
        /,
        *,
        file_id: str | None = None,
        video_codec: str | None = None,
        audio_codec: str | None = None,
        resolution: str | int | None = None,
        hash_string: str | None = None,
        only_truncate_stem: bool = True,
    ) -> str:
        calling_args = {name: value for name, value in locals().items() if value is not None and name not in ("self",)}
        include = PlaceHolderConfig()
        clean_name = sanitize_filename(Path(name).as_posix().replace("/", "-"))  # remove OS separators (if any)
        stem = Path(clean_name).stem.removesuffix(".")  # remove extensions (if any)
        truncate_len = constants.MAX_NAME_LENGTHS["FILE"] - len(ext)
        extra_info: list[str] = []

        if include.file_id and file_id:
            extra_info.append(file_id)
        if include.video_codec and video_codec:
            extra_info.append(video_codec)
        if include.audio_codec and audio_codec:
            extra_info.append(audio_codec)

        if include.resolution and resolution:
            if isinstance(resolution, str):
                if not resolution.removesuffix("p").isdigit():
                    assert resolution in VALID_RESOLUTION_NAMES, f"Invalid: {resolution = }"
                extra_info.append(resolution)
            else:
                extra_info.append(f"{resolution}p")

        if include.hash and hash_string:
            assert any(hash_string.startswith(x) for x in HASH_PREFIXES), f"Invalid: {hash_string = }"
            extra_info.append(hash_string)

        if extra_info:
            extra_info_str = "".join(f"[{info}]" for info in extra_info)
            clean_extra_info_str = sanitize_filename(extra_info_str)
            if clean_extra_info_str != extra_info_str:
                msg = (
                    f"Custom filename creation for {self.FOLDER_DOMAIN} seems to be broken. "
                    f"Important information was removed while creating a filename. "
                    f"Please report this as a bug at {NEW_ISSUE_URL}:\n{calling_args}"
                )
                log(msg, 30)

            if only_truncate_stem and (new_truncate_len := truncate_len - len(clean_extra_info_str) - 1) > 0:
                truncated_stem = f"{truncate_str(stem, new_truncate_len)} {clean_extra_info_str}"
            else:
                truncated_stem = truncate_str(f"{stem} {clean_extra_info_str}", truncate_len)

        else:
            truncated_stem = truncate_str(stem, truncate_len)

        return f"{truncated_stem}{ext}"


def make_scrape_mapper_keys(cls: type[Crawler] | Crawler) -> tuple[str, ...]:
    if cls.SUPPORTED_DOMAINS:
        hosts: SupportedDomains = cls.SUPPORTED_DOMAINS

    else:
        hosts = cls.DOMAIN or cls.PRIMARY_URL.host
    if isinstance(hosts, str):
        hosts = (hosts,)
    return tuple(sorted(host.removeprefix("www.") for host in hosts))


def pre_check_scrape_item(scrape_item: ScrapeItem) -> None:
    if scrape_item.url.path == "/":
        raise ValueError
