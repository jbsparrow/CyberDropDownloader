from __future__ import annotations

import asyncio
import re
from calendar import timegm
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from aiolimiter import AsyncLimiter
from bs4 import BeautifulSoup
from yarl import URL

from cyberdrop_dl.clients.errors import ScrapeError
from cyberdrop_dl.scraper.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.logger import log
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_filename_and_ext

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.utils.data_enums_classes.url_objects import ScrapeItem

DATE_PATTERN = re.compile(r"(\d+)\s*(weeks?|days?|hours?|minutes?|seconds?)", re.IGNORECASE)
MIN_RATE_LIMIT = 4  # per minute
MAX_WAIT = 120  # seconds
MAX_RETRIES = 3


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
        if any(part in scrape_item.url.parts for part in ("search", "categories", "favoritevideos")):
            await self.playlist(scrape_item)
        else:
            await self.video(scrape_item)

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a video."""
        if await self.check_complete_from_referer(scrape_item):
            return

        if not self.session_cookie:
            raise ScrapeError(401, "No cookies provided", origin=scrape_item)

        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)

        title = soup.select_one("title").text.rsplit(" : XXXBunker.com")[0].strip()
        try:
            relative_date_str = (
                soup.select_one("div.video-details").find("li", string="Date Added").find_next("li").text.strip()
            )
            date = await self.parse_relative_date(relative_date_str)
            scrape_item.possible_datetime = date
        except AttributeError:
            pass

        video_iframe = ajax_soup = None
        try:
            video_iframe = soup.select_one("div.player-frame iframe")
            video_iframe_url_str: str = video_iframe.get("data-src", "")
            video_iframe_url = self.parse_url(video_iframe_url_str)
            video_id = video_iframe_url.parts[-1]
            async with self.request_limiter:
                video_iframe_soup: BeautifulSoup = await self.client.get_soup(
                    self.domain,
                    video_iframe_url,
                    origin=scrape_item,
                )

            src = video_iframe_soup.select_one("source")
            src_url_str: str = src.get("src")
            src_url = self.parse_url(src_url_str)
            internal_id = src_url.query.get("id")

            if "internal" in src_url.parts:
                internal_id = video_id

            data = {"internalid": internal_id}

            async with self.request_limiter:
                ajax_dict = await self.client.post_data(self.domain, self.api_download, data=data, origin=scrape_item)

            ajax_soup = BeautifulSoup(ajax_dict["floater"], "html.parser")
            link_str: str = ajax_soup.select_one("a#download-download").get("href")
            link = self.parse_url(link_str)

        except (AttributeError, TypeError):
            if ajax_soup and "You must be registered to download this video" in ajax_soup.text:
                raise ScrapeError(403, "Invalid cookies, PHPSESSID", origin=scrape_item) from None

            if "TRAFFIC VERIFICATION" in soup.text:
                await self.adjust_rate_limit()
                raise ScrapeError(429, origin=scrape_item) from None
            raise ScrapeError(422, "Couldn't find video source", origin=scrape_item) from None

        # NOTE: hardcoding the extension to prevent quering the final server URL
        # final server URL is always different so it can not be saved to db.
        filename, ext = f"{video_id}.mp4", ".mp4"
        custom_filename, _ = get_filename_and_ext(f"{title} [{video_id}]{ext}")
        await self.handle_file(link, scrape_item, filename, ext, custom_filename=custom_filename)

    @error_handling_wrapper
    async def playlist(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a playlist."""
        if not self.session_cookie:
            raise ScrapeError(401, "No cookies provided", origin=scrape_item)

        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)

        if "favoritevideos" in scrape_item.url.parts:
            title = self.create_title(f"user {scrape_item.url.parts[2]} [favorites]")

        elif "search" in scrape_item.url.parts:
            title = self.create_title(f"{scrape_item.url.parts[2].replace('+', ' ')} [search]")

        elif len(scrape_item.url.parts) >= 2:
            title = self.create_title(f"{scrape_item.url.parts[2]} [categorie]")

        # Not a valid URL
        else:
            raise ScrapeError(400, "Unsupported URL format", origin=scrape_item)

        scrape_item.part_of_album = True

        async for soup in self.web_pager(scrape_item):
            videos = soup.select("a[data-anim='4']")
            for video in videos:
                link_str: str = video.get("href")
                if not link_str:
                    continue
                link = self.parse_url(link_str)
                new_scrape_item = self.create_scrape_item(scrape_item, link, title, add_parent=scrape_item.url)
                await self.video(new_scrape_item)

    async def web_pager(self, scrape_item: ScrapeItem) -> AsyncGenerator[BeautifulSoup]:
        """Generator of website pages."""
        page_url = scrape_item.url
        rate_limited = True
        while True:
            attempt = 1
            rate_limited = True
            soup = None
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
                raise ScrapeError(429, origin=scrape_item)

            next_page = soup.select_one("div.page-list")
            next_page = next_page.find("a", string="Next") if next_page else None
            yield soup
            if not next_page:
                break
            page_url_str: str = next_page.get("href")
            page_url = self.parse_url(page_url_str)

    @staticmethod
    async def parse_relative_date(relative_date: timedelta | str) -> int:
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
