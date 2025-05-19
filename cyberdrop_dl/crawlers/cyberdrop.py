from __future__ import annotations

from typing import TYPE_CHECKING

from aiolimiter import AsyncLimiter
from bs4 import BeautifulSoup
from yarl import URL

from cyberdrop_dl.crawlers.crawler import Crawler, create_task_id
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem
    from cyberdrop_dl.managers.manager import Manager

API_ENTRYPOINT = URL("https://api.cyberdrop.me/api/")


class Selectors:
    ALBUM_TITLE = "h1[id=title]"
    ALBUM_DATE = "p[class=title]"
    ALBUM_ITEM = "div[class*=image-container] a[class=image]"


_SELECTORS = Selectors()


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
            return await self.album(scrape_item)
        await self.file(scrape_item)

    @error_handling_wrapper
    async def album(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an album."""
        scrape_item.url = scrape_item.url.with_query("nojs")
        album_id = scrape_item.url.parts[2]

        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url)

        try:
            title: str = soup.select_one(_SELECTORS.ALBUM_TITLE).text  # type: ignore
            title = self.create_title(title, album_id)
            scrape_item.setup_as_album(title, album_id=album_id)
        except AttributeError:
            msg = "Unable to parse album information from response content"
            raise ScrapeError(422, msg) from None

        if date_tags := soup.select(_SELECTORS.ALBUM_DATE):
            scrape_item.possible_datetime = self.parse_date(date_tags[-1].text, "%d.%m.%Y")

        for _, new_scrape_item in self.iter_children(scrape_item, soup, _SELECTORS.ALBUM_ITEM):
            self.manager.task_group.create_task(self.run(new_scrape_item))

    @error_handling_wrapper
    async def file(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a file."""
        scrape_item.url = await self.get_stream_link(scrape_item.url)
        if await self.check_complete_from_referer(scrape_item):
            return

        file_id = scrape_item.url.name
        async with self.request_limiter:
            api_url = API_ENTRYPOINT / "file" / "info" / file_id
            json_resp = await self.client.get_json(self.domain, api_url)

        filename, ext = self.get_filename_and_ext(json_resp["name"])

        async with self.request_limiter:
            api_url = API_ENTRYPOINT / "file" / "auth" / file_id
            json_resp = await self.client.get_json(self.domain, api_url)

        link = self.parse_url(json_resp["url"])
        await self.handle_file(link, scrape_item, filename, ext)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    async def get_stream_link(self, url: URL) -> URL:
        """Gets the stream link for a given URL.

        NOTE: This makes a request to get the final URL (if necessary). Calling function must use `@error_handling_wrapper`"""
        assert url.host
        if any(part in url.parts for part in ("a", "f")):
            return url
        if url.host.count(".") > 1 or "e" in url.parts:
            return self.primary_base_domain / "f" / url.name
        response, _ = await self.client._get_response_and_soup(self.domain, url)
        return response.url
