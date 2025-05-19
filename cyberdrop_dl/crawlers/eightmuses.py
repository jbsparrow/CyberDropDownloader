from __future__ import annotations

from typing import TYPE_CHECKING

from yarl import URL

from cyberdrop_dl.crawlers.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem
    from cyberdrop_dl.managers.manager import Manager


TILE_SELECTOR = "a[class*=c-tile]"
IMAGE_SELECTOR = "div[class=image]"
TITLE_PARTS_SELECTOR = "div[class=top-menu-breadcrumb] > ol > li > a"


class EightMusesCrawler(Crawler):
    primary_base_domain = URL("https://comics.8muses.com")

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "8muses", "8Muses")

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""
        if "album" in scrape_item.url.parts:
            return await self.album(scrape_item)
        raise ValueError

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    @error_handling_wrapper
    async def album(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an album."""
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url)

        album_id = scrape_item.album_id
        if not album_id:
            title_parts = get_title_parts(soup)
            album_title = title_parts[-1]
            album_id = album_title.replace(" ", "-")
            title = self.create_title(album_title, scrape_item.album_id)
            scrape_item.setup_as_album(title, album_id=album_id)

        results = await self.get_album_results(album_id)

        for tile in soup.select(TILE_SELECTOR):
            tile_link = self.parse_url(tile.get("href"))  # type: ignore
            tile_title: str = tile.get("title", "")  # type: ignore
            image = tile.select_one(IMAGE_SELECTOR)
            is_new_album = image["itemtype"] == "https://schema.org/ImageGallery"  # type: ignore
            new_album_id = f"{scrape_item.album_id}/{tile_title.replace(' ', '-')}"
            new_scrape_item = scrape_item.create_child(tile_link, new_title_part=tile_title, album_id=new_album_id)
            if is_new_album:
                await self.album(new_scrape_item)
                continue

            image_link_str: str = image.select_one("img").get("data-src").replace("/th/", "/fm/")  # type: ignore
            image_link = self.parse_url(image_link_str)
            if not self.check_album_results(image_link, results):
                filename, ext = self.get_filename_and_ext(f"{tile_title}.jpg")
                await self.handle_file(image_link, new_scrape_item, filename, ext)
            scrape_item.add_children()


def get_title_parts(soup: BeautifulSoup) -> tuple[str, ...]:
    """Gets the album title, sub-album title, and comic title."""
    titles = soup.select(TITLE_PARTS_SELECTOR)[1:]
    return [title.text for title in titles]  # type: ignore
