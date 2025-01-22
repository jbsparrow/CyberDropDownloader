from __future__ import annotations

import asyncio
import copy
import re
from abc import ABC, abstractmethod
from dataclasses import field
from datetime import datetime
from functools import wraps
from typing import TYPE_CHECKING, Any, ClassVar, Protocol

from aiolimiter import AsyncLimiter
from bs4 import BeautifulSoup
from yarl import URL

from cyberdrop_dl.clients.errors import LoginError
from cyberdrop_dl.downloader.downloader import Downloader
from cyberdrop_dl.scraper.filters import set_return_value
from cyberdrop_dl.utils.data_enums_classes.url_objects import MediaItem, ScrapeItem
from cyberdrop_dl.utils.database.tables.history_table import get_db_path
from cyberdrop_dl.utils.logger import log
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_download_path, remove_file_id

if TYPE_CHECKING:
    from collections.abc import Callable

    from cyberdrop_dl.clients.scraper_client import ScraperClient
    from cyberdrop_dl.managers.manager import Manager


class Post(Protocol):
    number: int
    id: str
    title: str
    date: datetime | int


class Crawler(ABC):
    SUPPORTED_SITES: ClassVar[dict[str, list]] = {}
    domain = None
    primary_base_domain: URL = None
    DEFAULT_POST_TITLE_FORMAT = "{date} - {number} - {title}"

    def __init__(self, manager: Manager, domain: str, folder_domain: str | None = None) -> None:
        self.manager = manager
        self.downloader = field(init=False)
        self.scraping_progress = manager.progress_manager.scraping_progress
        self.client: ScraperClient = field(init=False)
        self._semaphore = asyncio.Semaphore(20)
        self.startup_lock = asyncio.Lock()
        self.request_limiter = AsyncLimiter(10, 1)
        self.ready: bool = False

        self.domain = domain
        self.folder_domain = folder_domain or domain.capitalize()

        self.logged_in = field(init=False)

        self.scraped_items: list = []
        self.waiting_items = 0

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
        self.waiting_items += 1
        async with self._semaphore:
            self.waiting_items -= 1
            if item.url.path_qs not in self.scraped_items:
                log(f"Scraping: {item.url}", 20)
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
    ) -> None:
        """Finishes handling the file and hands it off to the downloader."""
        if custom_filename:
            original_filename, filename = filename, custom_filename
        elif self.domain in ["cyberdrop"]:
            original_filename, filename = remove_file_id(self.manager, filename, ext)
        else:
            original_filename = filename

        download_folder = get_download_path(self.manager, scrape_item, self.folder_domain)
        media_item = MediaItem(
            url,
            scrape_item,
            download_folder,
            filename,
            original_filename,
            debrid_link,
        )

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

        self.manager.task_group.create_task(self.downloader.run(media_item))

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    async def check_skip_by_config(self, media_item: MediaItem) -> bool:
        settings = self.manager.config_manager.settings_data
        if (
            settings.download_options.skip_referer_seen_before
            and await self.manager.db_manager.temp_referer_table.check_referer(media_item.referer)
        ):
            log(f"Download skip {media_item.url} as referer has been seen before", 10)
            return True

        skip_hosts = settings.ignore_options.skip_hosts
        if skip_hosts and any(host in media_item.url.host for host in skip_hosts):
            log(f"Download skip {media_item.url} due to skip_hosts config", 10)
            return True

        only_hosts = settings.ignore_options.only_hosts
        if only_hosts and not any(host in media_item.url.host for host in only_hosts):
            log(f"Download skip {media_item.url} due to only_hosts config", 10)
            return True

        valid_regex_filter = self.manager.config_manager.valid_filename_filter_regex
        regex_filter = self.manager.config_manager.settings_data.ignore_options.filename_regex_filter

        if valid_regex_filter and re.search(regex_filter, media_item.filename):
            log(f"Download skip {media_item.url} due to filename regex filter config", 10)
            return True

        return False

    def check_post_number(self, post_number: int, current_post_number: int) -> tuple[bool, bool]:
        """Checks if the program should scrape the current post."""
        """Returns (scrape_post, continue_scraping)"""
        scrape_single_forum_post = self.manager.config_manager.settings_data.download_options.scrape_single_forum_post

        scrape_post = continue_scraping = True

        if scrape_single_forum_post:
            if not post_number or post_number == current_post_number:
                continue_scraping = False
            else:
                scrape_post = False

        elif post_number and post_number > current_post_number:
            scrape_post = False

        return scrape_post, continue_scraping

    def handle_external_links(self, scrape_item: ScrapeItem) -> None:
        """Maps external links to the scraper class."""
        self.manager.task_group.create_task(self.manager.scrape_mapper.filter_and_send_to_crawler(scrape_item))

    @error_handling_wrapper
    async def forum_login(
        self,
        login_url: URL,
        session_cookie: str,
        username: str,
        password: str,
        wait_time: int = 5,
    ) -> None:
        """Logs into a forum."""
        if session_cookie:
            self.client.client_manager.cookies.update_cookies(
                {"xf_user": session_cookie},
                response_url=URL("https://" + login_url.host),
            )
        if (not username or not password) and not session_cookie:
            log(f"Login wasn't provided for {login_url.host}", 30)
            raise LoginError(message="Login wasn't provided")
        attempt = 0

        while True:
            try:
                attempt += 1
                if attempt == 5:
                    raise LoginError(message="Failed to login after 5 attempts")

                assert login_url.host is not None

                await set_return_value(str(login_url), False, pop=False)
                await set_return_value(str(login_url / "login"), False, pop=False)

                text = await self.client.get_text(self.domain, login_url)
                if '<span class="p-navgroup-user-linkText">' in text or "You are already logged in." in text:
                    self.logged_in = True
                    return

                await asyncio.sleep(wait_time)
                soup = BeautifulSoup(text, "html.parser")

                inputs = soup.select("form input")
                data = {elem["name"]: elem["value"] for elem in inputs if elem.get("name") and elem.get("value")}
                data.update(
                    {"login": username, "password": password, "_xfRedirect": str(URL("https://" + login_url.host))},
                )
                await self.client.post_data(self.domain, login_url / "login", data=data, req_resp=False)
                await asyncio.sleep(wait_time)
                text = await self.client.get_text(self.domain, login_url)
                if '<span class="p-navgroup-user-linkText">' not in text or "You are already logged in." not in text:
                    continue
                self.logged_in = True
                break

            except asyncio.exceptions.TimeoutError:
                continue

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    async def check_complete_from_referer(self, scrape_item: ScrapeItem | URL) -> bool:
        """Checks if the scrape item has already been scraped."""
        url = scrape_item if isinstance(scrape_item, URL) else scrape_item.url
        check_complete = await self.manager.db_manager.history_table.check_complete_by_referer(self.domain, url)
        if check_complete:
            log(f"Skipping {url} as it has already been downloaded", 10)
            self.manager.progress_manager.download_progress.add_previously_completed()
            return True
        return False

    async def get_album_results(self, album_id: str) -> dict[Any, Any]:
        """Checks whether an album has completed given its domain and album id."""
        return await self.manager.db_manager.history_table.check_album(self.domain, album_id)

    def check_album_results(self, url: URL, album_results: dict[Any, Any]) -> bool:
        """Checks whether an album has completed given its domain and album id."""
        url_path = get_db_path(url.with_query(""), self.domain)
        if album_results and url_path in album_results and album_results[url_path] != 0:
            log(f"Skipping {url} as it has already been downloaded", 10)
            self.manager.progress_manager.download_progress.add_previously_completed()
            return True
        return False

    @staticmethod
    def create_scrape_item(
        parent_scrape_item: ScrapeItem,
        url: URL,
        new_title_part: str = "",
        part_of_album: bool = False,
        album_id: str | None = None,
        possible_datetime: int | None = None,
        add_parent: URL | None = None,
    ) -> ScrapeItem:
        """Creates a scrape item."""
        scrape_item = copy.deepcopy(parent_scrape_item)
        scrape_item.url = url
        if add_parent:
            scrape_item.parents.append(add_parent)
        if new_title_part:
            scrape_item.add_to_parent_title(new_title_part)
        scrape_item.part_of_album = part_of_album or scrape_item.part_of_album
        scrape_item.possible_datetime = possible_datetime or scrape_item.possible_datetime
        scrape_item.album_id = album_id or scrape_item.album_id
        return scrape_item

    def create_title(self, title: str, album_id: str | None = None, thread_id: str | None = None) -> str:
        """Creates the title for the scrape item."""
        download_options = self.manager.config_manager.settings_data.download_options
        if not title:
            title = "Untitled"

        title = title.strip()
        if download_options.include_album_id_in_folder_name and album_id:
            title = f"{title} {album_id}"

        if download_options.include_thread_id_in_folder_name and thread_id:
            title = f"{title} {thread_id}"

        if not download_options.remove_domains_from_folder_names:
            title = f"{title} ({self.folder_domain})"

        return title

    def add_separate_post_title(self, scrape_item: ScrapeItem, post: Post) -> None:
        if not self.manager.config_manager.settings_data.download_options.separate_posts:
            return
        title_format = self.manager.config_manager.settings_data.download_options.separate_posts_format
        if title_format.casefold() == "{default}":
            title_format = self.DEFAULT_POST_TITLE_FORMAT
        date = post.date
        if isinstance(post.date, int):
            date = datetime.fromtimestamp(date)
        if isinstance(date, datetime):
            date = date.isoformat()
        id = "Unknown" if post.id is None else post.id
        title = "Untitled" if post.title is None else post.title
        date = "NO_DATE" if date is None else date
        title = title_format.format(id=id, number=id, date=date, title=title)
        scrape_item.add_to_parent_title(title)

    def parse_url(self, link_str: str, relative_to: URL | None = None) -> URL:
        assert link_str
        assert isinstance(link_str, str)
        encoded = "%" in link_str
        base = relative_to or self.primary_base_domain
        new_url = URL(link_str, encoded=encoded)
        if not new_url.absolute:
            new_url = base.join(new_url)
        if not new_url.scheme:
            new_url = new_url.with_scheme(base.scheme or "https")
        return new_url


def create_task_id(func: Callable) -> Callable:
    """Wrapper handles task_id creation and removal for ScrapeItems"""

    @wraps(func)
    async def wrapper(self: Crawler, *args, **kwargs):
        scrape_item: ScrapeItem = args[0]
        task_id = self.scraping_progress.add_task(scrape_item.url)
        try:
            return await func(self, *args, **kwargs)
        finally:
            self.scraping_progress.remove_task(task_id)

    return wrapper
