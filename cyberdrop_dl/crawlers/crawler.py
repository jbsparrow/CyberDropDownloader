from __future__ import annotations

import asyncio
import calendar
import re
from abc import ABC, abstractmethod
from dataclasses import field
from datetime import datetime
from functools import wraps
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, ParamSpec, Protocol, TypeVar

from aiolimiter import AsyncLimiter
from dateutil import parser
from yarl import URL

from cyberdrop_dl.data_structures.url_objects import MediaItem, ScrapeItem
from cyberdrop_dl.downloader.downloader import Downloader
from cyberdrop_dl.scraper import filters
from cyberdrop_dl.types import TimeStamp, is_absolute_http_url
from cyberdrop_dl.utils import utilities
from cyberdrop_dl.utils.database.tables.history_table import get_db_path
from cyberdrop_dl.utils.logger import log, log_debug
from cyberdrop_dl.utils.utilities import (
    error_handling_wrapper,
    get_download_path,
    get_filename_and_ext,
    parse_url,
    remove_file_id,
)

_NEW_ISSUE_URL = "https://github.com/jbsparrow/CyberDropDownloader/issues/new/choose"

P = ParamSpec("P")
R = TypeVar("R")

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Awaitable, Callable, Coroutine, Generator

    from aiohttp_client_cache.response import AnyResponse
    from bs4 import BeautifulSoup, Tag

    from cyberdrop_dl.clients.scraper_client import ScraperClient
    from cyberdrop_dl.managers.manager import Manager

UNKNOWN_URL_PATH_MSG = "Unknown URL path"


class Post(Protocol):
    number: int
    id: str
    title: str
    date: datetime | int | None


class Crawler(ABC):
    SUPPORTED_SITES: ClassVar[dict[str, list[str]]] = {}
    primary_base_domain: ClassVar[URL] = None  # type: ignore
    DEFAULT_POST_TITLE_FORMAT: ClassVar[str] = "{date} - {number} - {title}"
    update_unsupported: ClassVar[bool] = False
    skip_pre_check: ClassVar[bool] = False
    next_page_selector: ClassVar[str] = ""
    scrape_prefix: ClassVar[str] = "Scraping:"
    scrape_mapper_domain: ClassVar[str] = ""
    domain: str = None  # type: ignore

    def __init__(self, manager: Manager, domain: str, folder_domain: str | None = None) -> None:
        self.manager = manager
        self.downloader = field(init=False)
        self.scraping_progress = manager.progress_manager.scraping_progress
        self.client: ScraperClient = field(init=False)
        self.startup_lock = asyncio.Lock()
        self.request_limiter = AsyncLimiter(10, 1)
        self.ready: bool = False
        self.domain = domain
        self.folder_domain = folder_domain or domain.capitalize()
        self.logged_in: bool = False
        self.scraped_items: list = []
        self.waiting_items = 0
        self.log = log
        self.log_debug = log_debug
        self.utils = utilities
        self._semaphore = asyncio.Semaphore(20)

    @property
    def name(self) -> str:
        return self.__class__.__name__.removesuffix("Crawler")

    @property
    def allow_no_extension(self) -> bool:
        return not self.manager.config_manager.settings_data.ignore_options.exclude_files_with_no_extension

    async def startup(self) -> None:
        """Starts the crawler."""
        async with self.startup_lock:
            if self.ready:
                return
            self.client = self.manager.client_manager.scraper_session
            self.downloader = Downloader(self.manager, self.domain)
            self.downloader.startup()
            await self.async_startup()
            self.ready = True

    async def async_startup(self) -> None: ...  # noqa: B027

    async def run(self, item: ScrapeItem) -> None:
        """Runs the crawler loop."""
        if not item.url.host:
            return

        await self.manager.states.RUNNING.wait()
        self.waiting_items += 1
        async with self._semaphore:
            self.waiting_items -= 1
            if item.url.path_qs not in self.scraped_items:
                log(f"{self.scrape_prefix} {item.url}", 20)
                self.scraped_items.append(item.url.path_qs)
                await self.fetch(item)
            else:
                log(f"Skipping {item.url} as it has already been scraped", 10)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @abstractmethod
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Director for scraping."""
        msg = "Must override in child class"
        raise NotImplementedError(msg)

    async def handle_file(
        self,
        url: URL,
        scrape_item: ScrapeItem,
        filename: str,
        ext: str,
        *,
        custom_filename: str | None = None,
        debrid_link: URL | None = None,
        m3u8_content: str = "",
    ) -> None:
        """Finishes handling the file and hands it off to the downloader."""
        await self.manager.states.RUNNING.wait()
        if custom_filename:
            original_filename, filename = filename, custom_filename
        elif self.domain in ["cyberdrop"]:
            original_filename, filename = remove_file_id(self.manager, filename, ext)
        else:
            original_filename = filename

        assert is_absolute_http_url(url)
        if isinstance(debrid_link, URL):
            assert is_absolute_http_url(debrid_link)
        download_folder = get_download_path(self.manager, scrape_item, self.folder_domain)
        media_item = MediaItem(url, scrape_item, download_folder, filename, original_filename, debrid_link, ext=ext)

        if media_item.datetime and not isinstance(media_item.datetime, int):
            msg = f"Invalid datetime from '{self.folder_domain}' crawler . Got {media_item.datetime!r}, expected int. "
            msg += "Please file a bug report at https://github.com/jbsparrow/CyberDropDownloader/issues/new/choose"
            log(msg, 30)

        check_complete = await self.manager.db_manager.history_table.check_complete(self.domain, url, scrape_item.url)
        if check_complete:
            if media_item.album_id:
                await self.manager.db_manager.history_table.set_album_id(self.domain, media_item)
            log(f"Skipping {url} as it has already been downloaded", 10)
            self.manager.progress_manager.download_progress.add_previously_completed()
            return

        if await self.check_skip_by_config(media_item):
            self.manager.progress_manager.download_progress.add_skipped()
            return

        if not m3u8_content:
            self.manager.task_group.create_task(self.downloader.run(media_item))
            return

        self.manager.task_group.create_task(self.downloader.download_hls(media_item, m3u8_content))

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

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
        downloaded = await self.manager.db_manager.history_table.check_complete_by_referer(self.domain, url)
        if downloaded:
            log(f"Skipping {url} as it has already been downloaded", 10)
            self.manager.progress_manager.download_progress.add_previously_completed()
            return True
        return False

    async def get_album_results(self, album_id: str) -> dict[str, int]:
        """Checks whether an album has completed given its domain and album id."""
        return await self.manager.db_manager.history_table.check_album(self.domain, album_id)

    def handle_external_links(self, scrape_item: ScrapeItem, reset: bool = False) -> None:
        """Maps external links to the scraper class."""
        if reset:
            scrape_item.reset()
        self.manager.task_group.create_task(self.manager.scrape_mapper.filter_and_send_to_crawler(scrape_item))

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

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
        url_path = get_db_path(url, self.domain)
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
            title = f"{title} ({self.folder_domain})"

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

        def _str(default: str, value: str | None) -> str:
            return default if value is None else value

        id = _str("Unknown", id)
        title = _str("Untitled", title)
        date_str = _str("NO_DATE", date_str)
        return title_format.format(id=id, date=date_str, title=title)

    def parse_url(self, link_str: str, relative_to: URL | None = None, *, trim: bool = True) -> URL:
        """Wrapper arround `utils.parse_url` to use `self.primary_base_domain` as base"""
        base = relative_to or self.primary_base_domain
        return parse_url(link_str, base, trim=trim)

    def update_cookies(self, cookies: dict, url: URL | None = None) -> None:
        """Update cookies for the provided URL

        If `url` is `None`, defaults to `self.primary_base_domain`
        """
        response_url = url or self.primary_base_domain
        self.client.client_manager.cookies.update_cookies(cookies, response_url)

    def iter_tags(
        self,
        soup: Tag,
        selector: str,
        /,
        attribute: str = "href",
        *,
        results: dict[str, int] | None = None,
    ) -> Generator[tuple[URL | None, URL]]:
        """Generates tuples with an URL from the `src` value of the first image tag (AKA the thumbnail) and an URL from the value of `attribute`

        :param results: must be the output of `self.get_album_results`.
        If provided, it will be used as a filter, to only yield items that has not been downloaded before"""
        album_results = results or {}

        for tag in soup.css.iselect(selector):
            link_str: str | None = tag.get(attribute)  # type: ignore
            if not link_str:
                continue
            link = self.parse_url(link_str)
            if self.check_album_results(link, album_results):
                continue
            if t_tag := tag.select_one("img"):
                thumb_str: str | None = t_tag.get("src")
            else:
                thumb_str = None
            thumb = self.parse_url(thumb_str) if thumb_str else None
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
    ) -> Generator[tuple[URL | None, ScrapeItem]]:
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

        page_url = url
        selector = next_page_selector or self.next_page_selector
        assert selector, f"No selector was provided and {self.domain} does define a next_page_selector"
        get_soup = self.client.get_soup_cffi if cffi else self.client.get_soup
        while True:
            async with self.request_limiter:
                soup: BeautifulSoup = await get_soup(self.domain, page_url)
            yield soup
            next_page = soup.select_one(selector)
            page_url_str: str | None = next_page.get("href") if next_page else None  # type: ignore
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
        msg = f"Date parsing for {self.domain} seems to be broken. Please report this as a bug at {_NEW_ISSUE_URL}"
        if not date_or_datetime:
            log(f"{msg}: Unable to extract date from soup", 40)
            return None
        try:
            if format:
                parsed_date = datetime.strptime(date_or_datetime, format)
            else:
                parsed_date = parser.parse(date_or_datetime)
        except (ValueError, TypeError, parser.ParserError) as e:
            log(f"{msg}: {e}", 40)
            return None
        else:
            return TimeStamp(calendar.timegm(parsed_date.timetuple()))

    def parse_soup_date(self, soup: Tag, selector: str, attribute: str, format: str | None = None, /):
        date_str: str = date_tag.get(attribute) if (date_tag := soup.select_one(selector)) else ""  # type: ignore
        return self.parse_date(date_str, format)

    @staticmethod
    def register_cache_filter(
        url: URL, filter_fn: Callable[[AnyResponse], bool] | Callable[[AnyResponse], Awaitable[bool]]
    ) -> None:
        assert url.host
        filters.cache_filter_functions[url.host] = filter_fn


def create_task_id(func: Callable[P, Coroutine[None, None, R]]) -> Callable[P, Coroutine[None, None, R | None]]:
    """Wrapper that handles `task_id` creation and removal for scrape items"""

    @wraps(func)
    async def wrapper(*args, **kwargs) -> R | None:
        self: Crawler = args[0]
        scrape_item: ScrapeItem = args[1]
        await self.manager.states.RUNNING.wait()
        task_id = self.scraping_progress.add_task(scrape_item.url)
        try:
            if not self.skip_pre_check:
                pre_check_scrape_item(scrape_item)
            return await func(*args, **kwargs)
        except ValueError:
            log(f"Scrape Failed: {UNKNOWN_URL_PATH_MSG}: {scrape_item.url}", 40)
            self.manager.progress_manager.scrape_stats_progress.add_failure(UNKNOWN_URL_PATH_MSG)
            await self.manager.log_manager.write_scrape_error_log(scrape_item.url, UNKNOWN_URL_PATH_MSG)
        finally:
            self.scraping_progress.remove_task(task_id)

    return wrapper


def pre_check_scrape_item(scrape_item: ScrapeItem) -> None:
    if scrape_item.url.path == "/":
        raise ValueError
