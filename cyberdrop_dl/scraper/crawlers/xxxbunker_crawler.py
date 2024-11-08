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
from cyberdrop_dl.scraper.crawler import Crawler
from cyberdrop_dl.utils.logger import log
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_filename_and_ext

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.utils.dataclasses.url_objects import ScrapeItem

DATE_PATTERN = re.compile(r"(\d+)\s*(weeks?|days?|hours?|minutes?|seconds?)", re.IGNORECASE)
MIN_RATE_LIMIT = 4  # per minute
MAX_WAIT = 120  # seconds
MAX_RETRIES = 3


class XXXBunkerCrawler(Crawler):
    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "xxxbunker", "XXXBunker")
        self.primary_base_domain = URL("https://xxxbunker.com")
        self.api_download = URL("https://xxxbunker.com/ajax/downloadpopup")
        self.rate_limit = self.wait_time = 10
        self.request_limiter = AsyncLimiter(self.rate_limit, 60)
        self.session_cookie = None

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        task_id = self.scraping_progress.add_task(scrape_item.url)

        # Old behavior, not worth it with such a bad rate_limit: modify URL to always start on page 1
        """
        new_parts = [part for part in scrape_item.url.parts[1:] if "page-" not in part]
        scrape_item.url = scrape_item.url.with_path("/".join(new_parts)).with_query(scrape_item.url.query)
        """
        if self.session_cookie is None:
            await self.check_session_cookie()

        if any(part in scrape_item.url.parts for part in ("search", "categories", "favoritevideos")):
            await self.playlist(scrape_item)
        else:
            await self.video(scrape_item)

        self.scraping_progress.remove_task(task_id)

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
            video_iframe_url = URL(video_iframe.get("data-src"))
            video_id = video_iframe_url.parts[-1]
            async with self.request_limiter:
                video_iframe_soup: BeautifulSoup = await self.client.get_soup(
                    self.domain,
                    video_iframe_url,
                    origin=scrape_item,
                )

            src = video_iframe_soup.select_one("source")
            src_url = URL(src.get("src"))
            internal_id = src_url.query.get("id")

            if "internal" in src_url.parts:
                internal_id = video_id

            data = {"internalid": internal_id}

            async with self.request_limiter:
                ajax_dict = await self.client.post_data(self.domain, self.api_download, data=data, origin=scrape_item)

            ajax_soup = BeautifulSoup(ajax_dict["floater"], "html.parser")
            link = URL(ajax_soup.select_one("a#download-download").get("href"))

        except (AttributeError, TypeError):
            if ajax_soup and "You must be registered to download this video" in ajax_soup.text:
                raise ScrapeError(403, f"Invalid PHPSESSID: {scrape_item.url}", origin=scrape_item) from None

            if "TRAFFIC VERIFICATION" in soup.text:
                await asyncio.sleep(self.wait_time)
                self.wait_time = min(self.wait_time + 10, MAX_WAIT)
                self.rate_limit = max(self.rate_limit * 0.8, MIN_RATE_LIMIT)
                self.request_limiter = AsyncLimiter(self.rate_limit, 60)
                raise ScrapeError(429, f"Too many request: {scrape_item.url}", origin=scrape_item) from None
            raise ScrapeError(404, f"Could not find video source for {scrape_item.url}", origin=scrape_item) from None

        # NOTE: hardcoding the extension to prevent quering the final server URL
        # final server URL is always different so it can not be saved to db.
        filename, ext = f"{video_id}.mp4", ".mp4"
        custom_file_name, _ = get_filename_and_ext(f"{title} [{video_id}]{ext}")
        await self.handle_file(link, scrape_item, filename, ext, custom_file_name)

    @error_handling_wrapper
    async def playlist(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a playlist."""
        if not self.session_cookie:
            raise ScrapeError(401, "No cookies provided", origin=scrape_item)

        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)

        if "favoritevideos" in scrape_item.url.parts:
            title = self.create_title(f"user {scrape_item.url.parts[2]} [favorites]", None, None)

        elif "search" in scrape_item.url.parts:
            title = self.create_title(f"{scrape_item.url.parts[2].replace('+', ' ')} [search]", None, None)

        elif len(scrape_item.url.parts) >= 2:
            title = self.create_title(f"{scrape_item.url.parts[2]} [categorie]", None, None)

        # Not a valid URL
        else:
            raise ScrapeError(400, f"Unsupported URL format: {scrape_item.url}", origin=scrape_item)

        scrape_item.part_of_album = True

        async for soup in self.web_pager(scrape_item.url):
            videos = soup.select("a[data-anim='4']")
            for video in videos:
                link = video.get("href")
                if not link:
                    continue

                if link.startswith("/"):
                    link = self.primary_base_domain / link[1:]

                link = URL(link)
                new_scrape_item = self.create_scrape_item(scrape_item, link, title, add_parent=scrape_item.url)
                await self.video(new_scrape_item)

    async def web_pager(self, url: URL) -> AsyncGenerator[BeautifulSoup]:
        """Generator of website pages."""
        page_url = url
        rate_limited = True
        while True:
            attempt = 1
            rate_limited = True
            soup = None
            log(f"Current page: {page_url}", 10)
            while rate_limited and attempt <= MAX_RETRIES:
                async with self.request_limiter:
                    soup: BeautifulSoup = await self.client.get_soup(self.domain, page_url)
                await asyncio.sleep(self.wait_time)

                if "TRAFFIC VERIFICATION" not in soup.text:
                    rate_limited = False
                    break

                self.wait_time = min(self.wait_time + 10, MAX_WAIT)
                self.rate_limit = max(self.rate_limit * 0.8, MIN_RATE_LIMIT)
                self.request_limiter = AsyncLimiter(self.rate_limit, 60)
                log(f"Rate limited: {page_url}, retrying in {self.wait_time} seconds")
                attempt += 1
                await asyncio.sleep(self.wait_time)

            if rate_limited:
                raise ScrapeError(429, f"Too many request: {url}")

            next_page = soup.select_one("div.page-list")
            next_page = next_page.find("a", string="Next") if next_page else None
            yield soup
            if next_page:
                page_url = next_page.get("href")
                if page_url:
                    if page_url.startswith("/"):
                        page_url = self.primary_base_domain / page_url[1:]
                    page_url = URL(page_url)
                    continue
            break

    @staticmethod
    async def parse_relative_date(relative_date: timedelta | str) -> int:
        """Parses `datetime.timedelta` or `string` in a timedelta format. Returns `now() - parsed_timedelta` as an unix timestamp."""
        if isinstance(relative_date, str):
            time_str = relative_date.casefold()
            matches: list[str] = re.findall(DATE_PATTERN, time_str)

            # Assume today
            time_dict = {"days": 0}

            for value, unit in matches:
                value = int(value)
                unit = unit.lower()
                time_dict[unit] = value

            relative_date = timedelta(**time_dict)

        date = datetime.now() - relative_date
        return timegm(date.timetuple())

    async def check_session_cookie(self) -> None:
        """Get Cookie from config file."""
        self.session_cookie = self.manager.config_manager.authentication_data["XXXBunker"]["PHPSESSID"]
        if not self.session_cookie:
            self.session_cookie = ""
            return

        self.client.client_manager.cookies.update_cookies(
            {"PHPSESSID": self.session_cookie},
            response_url=self.primary_base_domain,
        )
