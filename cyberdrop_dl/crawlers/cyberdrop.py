from __future__ import annotations

import calendar
import datetime
import re
from typing import TYPE_CHECKING

from aiolimiter import AsyncLimiter
from bs4 import BeautifulSoup
from yarl import URL

from cyberdrop_dl.clients.errors import ScrapeError
from cyberdrop_dl.crawlers.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.utils.data_enums_classes.url_objects import ScrapeItem

CDN_POSSIBILITIES = re.compile(r"^(?:(?:k1)[0-9]{0,2})(?:redir)?\.cyberdrop?\.[a-z]{2,3}$")
API_ENTRYPOINT = URL("https://api.cyberdrop.me/api/")
ALBUM_TITLE_SELECTOR = "h1[id=title]"
ALBUM_DATE_SELECTOR = "p[class=title]"
ALBUM_ITEM_SELECTOR = "div[class*=image-container] a[class=image]"


class CyberdropCrawler(Crawler):
    primary_base_domain = URL("https://cyberdrop.me/")

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "cyberdrop", "Cyberdrop")
        self.request_limiter = AsyncLimiter(1, 2)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        if "a" in scrape_item.url.parts:
            scrape_item.url = scrape_item.url.with_query("nojs")
            return await self.album(scrape_item)
        await self.file(scrape_item)

    @error_handling_wrapper
    async def album(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an album."""
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url)
        album_id = scrape_item.url.parts[2]

        try:
            title = self.create_title(soup.select_one(ALBUM_TITLE_SELECTOR).text, album_id)  # type: ignore
            scrape_item.setup_as_album(title, album_id=album_id)
        except AttributeError:
            msg = "Unable to parse album information from response content"
            raise ScrapeError(422, msg) from None

        if date_tags := soup.select(ALBUM_DATE_SELECTOR):
            scrape_item.possible_datetime = parse_datetime(date_tags[-1].text)

        for _, new_scrape_item in self.iter_children(scrape_item, soup, ALBUM_ITEM_SELECTOR):
            self.manager.task_group.create_task(self.run(new_scrape_item))

    @error_handling_wrapper
    async def file(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a file."""
        scrape_item.url = await self.get_stream_link(scrape_item.url)
        if await self.check_complete_from_referer(scrape_item):
            return

        async with self.request_limiter:
            api_url = API_ENTRYPOINT / "file" / "info" / scrape_item.url.path[3:]
            json_resp = await self.client.get_json(self.domain, api_url)

        filename, ext = self.get_filename_and_ext(json_resp["name"])

        async with self.request_limiter:
            api_url = API_ENTRYPOINT / "file" / "auth" / scrape_item.url.path[3:]
            json_resp = await self.client.get_json(self.domain, api_url)

        link = self.parse_url(json_resp["url"])
        await self.handle_file(link, scrape_item, filename, ext)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    async def get_stream_link(self, url: URL) -> URL:
        """Gets the stream link for a given URL.

        NOTE: This makes a request to get the final URL (if necessary). Calling function must use `@error_handling_wrapper`"""
        if any(part in url.parts for part in ("a", "f")):
            return url
        if is_cdn(url) or "e" in url.parts:
            return self.primary_base_domain / "f" / url.name
        _, streaming_url = await self.client.get_soup_and_return_url(self.domain, url)
        return streaming_url


def is_cdn(url: URL) -> bool:
    """Checks if a given URL is from a CDN."""
    assert url.host
    return bool(re.match(CDN_POSSIBILITIES, url.host))


def parse_datetime(date: str) -> int:
    """Parses a datetime string into a unix timestamp."""
    parsed_date = datetime.datetime.strptime(date, "%d.%m.%Y")
    return calendar.timegm(parsed_date.timetuple())
