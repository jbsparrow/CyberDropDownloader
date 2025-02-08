from __future__ import annotations

from typing import TYPE_CHECKING

from yarl import URL

from cyberdrop_dl.scraper.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.data_enums_classes.url_objects import FILE_HOST_ALBUM, ScrapeItem
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_filename_and_ext

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.managers.manager import Manager


class PixHostCrawler(Crawler):
    primary_base_domain = URL("https://pixhost.to/")
    update_unsupported = True

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "pixhost", "PixHost")

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        if "gallery" in scrape_item.url.parts:
            await self.gallery(scrape_item)
        elif "show" in scrape_item.url.parts:
            await self.image(scrape_item)
        else:
            raise ValueError

    @error_handling_wrapper
    async def gallery(self, scrape_item: ScrapeItem) -> None:
        """Scrapes a gallery."""
        scrape_item.set_type(FILE_HOST_ALBUM, self.manager)
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)

        title = soup.select_one("a[class=link] h2").text
        scrape_item.add_to_parent_title(f"{title} (PixHost)")

        images = soup.select("div[class=images] a img")
        for image in images:
            link_str: str = image.get("src")
            if not link_str:
                continue
            link_str = link_str.replace("https://t", "https://img").replace("/thumbs/", "/images/")
            link = self.parse_url(link_str)
            filename, ext = get_filename_and_ext(link.name)
            await self.handle_file(link, scrape_item, filename, ext)
            scrape_item.add_children()

    @error_handling_wrapper
    async def image(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an image."""
        if await self.check_complete_from_referer(scrape_item):
            return

        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)

        link_str: str = soup.select_one("img[class=image-img]").get("src")
        link = self.parse_url(link_str)
        filename, ext = get_filename_and_ext(link.name)
        await self.handle_file(link, scrape_item, filename, ext)
