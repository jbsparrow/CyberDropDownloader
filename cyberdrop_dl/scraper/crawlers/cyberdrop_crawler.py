from __future__ import annotations

import calendar
import datetime
import re
from typing import TYPE_CHECKING

from aiolimiter import AsyncLimiter
from bs4 import BeautifulSoup
from yarl import URL

from cyberdrop_dl.clients.errors import ScrapeError
from cyberdrop_dl.scraper.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.data_enums_classes.url_objects import FILE_HOST_ALBUM, ScrapeItem
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_filename_and_ext

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.managers.manager import Manager

CDN_POSSIBILITIES = re.compile(r"^(?:(?:k1)[0-9]{0,2})(?:redir)?\.cyberdrop?\.[a-z]{2,3}$")


class CyberdropCrawler(Crawler):
    primary_base_domain = URL("https://cyberdrop.me/")

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "cyberdrop", "Cyberdrop")
        self.api_url = URL("https://api.cyberdrop.me/api/")
        self.request_limiter = AsyncLimiter(1, 2)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        if "a" in scrape_item.url.parts:
            scrape_item.url = scrape_item.url.with_query("nojs")
            await self.album(scrape_item)
        else:
            await self.file(scrape_item)

    @error_handling_wrapper
    async def album(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an album."""
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)
        scrape_item.set_type(FILE_HOST_ALBUM, self.manager)

        scrape_item.album_id = scrape_item.url.parts[2]
        scrape_item.part_of_album = True
        date = title = None

        try:
            title = self.create_title(soup.select_one("h1[id=title]").text, scrape_item.album_id)
        except AttributeError:
            msg = "Unable to parse album information from response content"
            raise ScrapeError(422, msg, origin=scrape_item) from None

        date = soup.select("p[class=title]")
        if date:
            date = self.parse_datetime(date[-1].text)

        links = soup.select("div[class*=image-container] a[class=image]")
        for link in links:
            link_str: str = link.get("href")
            link = self.parse_url(link_str)

            new_scrape_item = self.create_scrape_item(
                scrape_item,
                link,
                title,
                part_of_album=True,
                possible_datetime=date,
                add_parent=scrape_item.url,
            )
            self.manager.task_group.create_task(self.run(new_scrape_item))
            scrape_item.add_children()

    @error_handling_wrapper
    async def file(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a file."""
        scrape_item.url = await self.get_stream_link(scrape_item.url)
        if await self.check_complete_from_referer(scrape_item):
            return

        async with self.request_limiter:
            api_url = self.api_url / "file" / "info" / scrape_item.url.path[3:]
            JSON_Resp = await self.client.get_json(self.domain, api_url, origin=scrape_item)

        filename, ext = get_filename_and_ext(JSON_Resp["name"])

        async with self.request_limiter:
            api_url = self.api_url / "file" / "auth" / scrape_item.url.path[3:]
            JSON_Resp = await self.client.get_json(self.domain, api_url, origin=scrape_item)

        link_str: str = JSON_Resp["url"]
        link = self.parse_url(link_str)
        await self.handle_file(link, scrape_item, filename, ext)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    async def get_stream_link(self, url: URL) -> URL:
        """Gets the stream link for a given URL.

        NOTE: This makes a request to get the final URL (if necessary). Calling function must use `@error_handling_wrapper`

        """
        if any(part in url.parts for part in ("a", "f")):
            return url

        if self.is_cdn(url) or "e" in url.parts:
            return self.primary_base_domain / "f" / url.parts[-1]

        _, streaming_url = await self.client.get_soup_and_return_url(self.domain, url)

        return streaming_url

    @staticmethod
    def is_cdn(url: URL) -> bool:
        """Checks if a given URL is from a CDN."""
        return bool(re.match(CDN_POSSIBILITIES, url.host))

    @staticmethod
    def parse_datetime(date: str) -> int:
        """Parses a datetime string into a unix timestamp."""
        parsed_date = datetime.datetime.strptime(date, "%d.%m.%Y")
        return calendar.timegm(parsed_date.timetuple())
