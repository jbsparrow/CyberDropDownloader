from __future__ import annotations

from typing import TYPE_CHECKING

from yarl import URL

from cyberdrop_dl.scraper.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.data_enums_classes.url_objects import FILE_HOST_ALBUM, ScrapeItem
from cyberdrop_dl.utils.logger import log
from cyberdrop_dl.utils.utilities import error_handling_wrapper, get_filename_and_ext

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.managers.manager import Manager


class EightMusesCrawler(Crawler):
    primary_base_domain = URL("https://comics.8muses.com")

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "8muses", "8Muses")

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        if "album" in scrape_item.url.parts:
            await self.album(scrape_item)
        else:
            log(f"Scrape Failed: Unknown URL path: {scrape_item.url}", 40)
            return

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @error_handling_wrapper
    async def album(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an album."""
        scrape_item.set_type(FILE_HOST_ALBUM, self.manager)
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)

        if not scrape_item.parents:
            title_parts = await self.get_title_parts(soup)
            album_title = title_parts[-1]
            scrape_item.album_id = album_title.replace(" ", "-")
            scrape_item.add_to_parent_title(album_title)

        tiles = soup.select("a[class*=c-tile]")
        for tile in tiles:
            href = tile.get("href")
            if href:
                tile_link = self.parse_url(href)
            else:
                continue
            tile_title = tile.get("title", "")

            image = tile.select_one("div[class=image]")
            itemType = image.get("itemtype")
            if itemType == "https://schema.org/ImageGallery":
                new_scrape_item = self.create_scrape_item(
                    scrape_item,
                    tile_link,
                    tile_title,
                    True,
                    f'{scrape_item.album_id}/{tile_title.replace(" ", "-")}',
                    add_parent=scrape_item.url,
                )
                await self.album(new_scrape_item)
            else:
                filename, ext = get_filename_and_ext(f"{tile_title}.jpg")
                image_link = self.parse_url(image.select_one("img").get("data-src").replace("/th/", "/fm/"))
                new_scrape_item = self.create_scrape_item(
                    scrape_item,
                    tile_link,
                    tile_title,
                    False,
                    f'{scrape_item.album_id}/{tile_title.replace(" ", "-")}',
                    add_parent=scrape_item.url,
                )
                await self.handle_file(image_link, scrape_item, filename, ext)
                scrape_item.add_children()

    async def get_title_parts(self, soup: BeautifulSoup) -> tuple:
        """Gets the album title, sub-album title, and comic title."""
        titles = soup.select("div[class=top-menu-breadcrumb] > ol > li > a")[1:]
        title_parts = [title.text for title in titles]

        return title_parts
