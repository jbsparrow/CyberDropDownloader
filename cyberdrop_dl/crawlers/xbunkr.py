from __future__ import annotations

from typing import TYPE_CHECKING

from yarl import URL

from cyberdrop_dl.clients.errors import NoExtensionError
from cyberdrop_dl.crawlers.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.data_enums_classes.url_objects import FILE_HOST_ALBUM, ScrapeItem
from cyberdrop_dl.utils.logger import log
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.managers.manager import Manager


class XBunkrCrawler(Crawler):
    primary_base_domain = URL("https://xbunkr.com")

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "xbunkr", "XBunkr")

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        if "media" in scrape_item.url.host:
            filename, ext = self.get_filename_and_ext(scrape_item.url.name)
            await self.handle_file(scrape_item.url, scrape_item, filename, ext)
        else:
            await self.album(scrape_item)

    @error_handling_wrapper
    async def album(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a profile."""
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)

        scrape_item.album_id = scrape_item.url.parts[2]
        scrape_item.part_of_album = True
        scrape_item.set_type(FILE_HOST_ALBUM, self.manager)
        title = self.create_title(soup.select_one("h1[id=title]").text, scrape_item.album_id)

        links = soup.select("a[class=image]")
        for link in links:
            link_str: str = link.get("href")
            assert link_str
            link = self.parse_url(link_str)
            try:
                filename, ext = self.get_filename_and_ext(link.name)
            except NoExtensionError:
                log(f"Couldn't get extension for {link}", 40)
                continue
            new_scrape_item = self.create_scrape_item(scrape_item, link, title, True, add_parent=scrape_item.url)
            await self.handle_file(link, new_scrape_item, filename, ext)
            scrape_item.add_children()
