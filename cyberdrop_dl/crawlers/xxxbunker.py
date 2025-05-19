from __future__ import annotations

import asyncio
import re
from calendar import timegm
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from aiolimiter import AsyncLimiter
from bs4 import BeautifulSoup
from yarl import URL

from cyberdrop_dl.crawlers.crawler import Crawler, create_task_id
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.utils.logger import log
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem
    from cyberdrop_dl.managers.manager import Manager

DATE_PATTERN = re.compile(r"(\d+)\s*(weeks?|days?|hours?|minutes?|seconds?)", re.IGNORECASE)
MIN_RATE_LIMIT = 4  # per minute
MAX_WAIT = 120  # seconds
MAX_RETRIES = 3

VIDEOS_SELECTOR = "a[data-anim='4']"
DATE_SELECTOR = "div.video-details li:contains('Date Added') + li"
VIDEO_IFRAME_SELECTOR = "div.player-frame iframe"
DOWNLOAD_URL_SELECTOR = "a#download-download"
NEXT_PAGE_SELECTOR = "div.page-list a:contains('next')"
PLAYLIST_PARTS = ("search", "categories", "favoritevideos")


class XXXBunkerCrawler(Crawler):
    primary_base_domain = URL("https://xxxbunker.com")

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "xxxbunker", "XXXBunker")
        self.api_download = URL("https://xxxbunker.com/ajax/downloadpopup")
        self.rate_limit = self.wait_time = 10
        self.request_limiter = AsyncLimiter(self.rate_limit, 60)
        self.session_cookie = None

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    async def async_startup(self) -> None:
        await self.check_session_cookie()

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""

        # Old behavior, not worth it with such a bad rate_limit: modify URL to always start on page 1
        """
        new_parts = [part for part in scrape_item.url.parts[1:] if "page-" not in part]
        scrape_item.url = scrape_item.url.with_path("/".join(new_parts)).with_query(scrape_item.url.query)
        """
        if any(part in scrape_item.url.parts for part in PLAYLIST_PARTS):
            return await self.playlist(scrape_item)
        await self.video(scrape_item)

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a video."""
        if await self.check_complete_from_referer(scrape_item):
            return

        if not self.session_cookie:
            raise ScrapeError(401, "No cookies provided")

        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url)

        title = soup.select_one("title").text.rsplit(" : XXXBunker.com", 1)[0].strip()  # type: ignore
        if date_tag := soup.select_one(DATE_SELECTOR):
            scrape_item.possible_datetime = parse_relative_date(date_tag.text.strip())

        video_soup = None
        try:
            iframe = soup.select_one(VIDEO_IFRAME_SELECTOR)
            iframe_url = self.parse_url(iframe["data-src"])  # type: ignore
            video_id = iframe_url.parts[-1]
            async with self.request_limiter:
                iframe_soup: BeautifulSoup = await self.client.get_soup(self.domain, iframe_url)

            video_tag = iframe_soup.select_one("source")
            video_url = self.parse_url(video_tag[video_tag])  # type: ignore
            internal_id = video_url.query.get("id")

            if "internal" in video_url.parts:
                internal_id = video_id

            data = {"internalid": internal_id}

            async with self.request_limiter:
                json_resp = await self.client.post_data(self.domain, self.api_download, data=data)

            video_soup = BeautifulSoup(json_resp["floater"], "html.parser")
            link_str: str = video_soup.select_one(DOWNLOAD_URL_SELECTOR)["href"]  # type: ignore
            link = self.parse_url(link_str)

        except (AttributeError, TypeError):
            if video_soup and "You must be registered to download this video" in video_soup.text:
                raise ScrapeError(403, "Invalid cookies, PHPSESSID") from None

            if "TRAFFIC VERIFICATION" in soup.text:
                await self.adjust_rate_limit()
                raise ScrapeError(429) from None
            raise ScrapeError(422, "Couldn't find video source") from None

        filename, ext = f"{video_id}.mp4", ".mp4"
        custom_filename, _ = self.get_filename_and_ext(f"{title} [{video_id}]{ext}")
        await self.handle_file(link, scrape_item, filename, ext, custom_filename=custom_filename)

    @error_handling_wrapper
    async def playlist(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a playlist."""
        if not self.session_cookie:
            raise ScrapeError(401, "No cookies provided")

        name = scrape_item.url.parts[2]
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url)

        if "favoritevideos" in scrape_item.url.parts:
            title = self.create_title(f"user {name} [favorites]")
        elif "search" in scrape_item.url.parts:
            title = self.create_title(f"{name.replace('+', ' ')} [search]")
        elif len(scrape_item.url.parts) >= 2:
            title = self.create_title(f"{name} [category]")
        else:
            # Not a valid URL
            raise ScrapeError(400, "Unsupported URL format")

        scrape_item.setup_as_album(title)

        async for soup in self.web_pager(scrape_item):
            for _, new_scrape_item in self.iter_children(scrape_item, soup, VIDEOS_SELECTOR):
                self.manager.task_group.create_task(self.run(new_scrape_item))

    async def web_pager(self, scrape_item: ScrapeItem) -> AsyncGenerator[BeautifulSoup]:
        """Generator of website pages."""
        page_url = scrape_item.url
        while True:
            attempt = 1
            rate_limited = True
            while rate_limited and attempt <= MAX_RETRIES:
                async with self.request_limiter:
                    soup: BeautifulSoup = await self.client.get_soup(self.domain, page_url)
                await asyncio.sleep(self.wait_time)

                if "TRAFFIC VERIFICATION" not in soup.text:
                    rate_limited = False
                    break

                await self.adjust_rate_limit()
                log(f"Rate limited: {page_url}, retrying in {self.wait_time} seconds")
                attempt += 1
                await asyncio.sleep(self.wait_time)

            if rate_limited:
                raise ScrapeError(429)

            page_url_str: str | None = next_page["href"] if (next_page := soup.select_one(NEXT_PAGE_SELECTOR)) else None  # type: ignore
            yield soup
            if not page_url_str:
                break
            page_url = self.parse_url(page_url_str)

    async def adjust_rate_limit(self):
        await asyncio.sleep(self.wait_time)
        self.wait_time = min(self.wait_time + 10, MAX_WAIT)
        self.rate_limit = max(self.rate_limit * 0.8, MIN_RATE_LIMIT)
        self.request_limiter = AsyncLimiter(self.rate_limit, 60)

    async def check_session_cookie(self) -> None:
        """Get Cookie from config file."""
        self.session_cookie = self.manager.config_manager.authentication_data.xxxbunker.PHPSESSID
        if not self.session_cookie:
            self.session_cookie = ""
            return

        cookies = {"PHPSESSID": self.session_cookie}
        self.update_cookies(cookies)


def parse_relative_date(relative_date: timedelta | str) -> int:
    """Parses `datetime.timedelta` or `string` in a timedelta format. Returns `now() - parsed_timedelta` as an unix timestamp."""
    if isinstance(relative_date, str):
        time_str = relative_date.casefold()
        matches: list[str] = re.findall(DATE_PATTERN, time_str)
        time_dict = {"days": 0}

        for value, unit in matches:
            value = int(value)
            unit = unit.lower()
            time_dict[unit] = value

        relative_date = timedelta(**time_dict)

    date = datetime.now() - relative_date
    return timegm(date.timetuple())
