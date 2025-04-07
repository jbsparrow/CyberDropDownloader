from __future__ import annotations

from typing import TYPE_CHECKING

from yarl import URL

from cyberdrop_dl.crawlers.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.data_enums_classes.url_objects import FILE_HOST_ALBUM, ScrapeItem
from cyberdrop_dl.utils.utilities import error_handling_wrapper

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
        if "album" not in scrape_item.url.parts:
            raise ValueError
        await self.album(scrape_item)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @error_handling_wrapper
    async def album(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an album."""
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url, origin=scrape_item)

        if not scrape_item.album_id:
            scrape_item.set_type(FILE_HOST_ALBUM, self.manager)
            title_parts = self.get_title_parts(soup)
            album_title = title_parts[-1]
            scrape_item.album_id = album_title.replace(" ", "-")
            title = self.create_title(album_title, scrape_item.album_id)
            scrape_item.add_to_parent_title(title)

        results = await self.get_album_results(scrape_item.album_id)

        tiles = soup.select("a[class*=c-tile]")
        for tile in tiles:
            tile_link_str: str = tile.get("href")
            if not tile_link_str:
                continue
            tile_link = self.parse_url(tile_link_str)
            tile_title = tile.get("title", "")

            image = tile.select_one("div[class=image]")
            itemType = image.get("itemtype")
            part_of_album = itemType == "https://schema.org/ImageGallery"
            new_scrape_item = self.create_scrape_item(
                scrape_item,
                tile_link,
                tile_title,
                part_of_album=part_of_album,
                album_id=f"{scrape_item.album_id}/{tile_title.replace(' ', '-')}",
                add_parent=scrape_item.url,
            )
            if part_of_album:
                await self.album(new_scrape_item)
                continue

            filename, ext = self.get_filename_and_ext(f"{tile_title}.jpg")
            image_link_str: str = image.select_one("img").get("data-src").replace("/th/", "/fm/")
            image_link = self.parse_url(image_link_str)
            if not self.check_album_results(image_link, results):
                await self.handle_file(image_link, new_scrape_item, filename, ext)
            scrape_item.add_children()


def get_title_parts(soup: BeautifulSoup) -> tuple:
    """Gets the album title, sub-album title, and comic title."""
    titles = soup.select("div[class=top-menu-breadcrumb] > ol > li > a")[1:]
    return [title.text for title in titles]
