from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import FILE_HOST_ALBUM, AbsoluteHttpURL, ScrapeItem
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.utils import css
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

PRIMARY_URL = AbsoluteHttpURL("https://imgbox.com")
IMAGES_SELECTOR = "div#gallery-view-content img"
IMAGE_SELECTOR = "img[id=img]"
ALBUM_TITLE_SELECTOR = "div[id=gallery-view] h1"


class ImgBoxCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {"Album": "/g/...", "Image": "/...", "Direct links": ""}
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    DOMAIN: ClassVar[str] = "imgbox"
    FOLDER_DOMAIN: ClassVar[str] = "ImgBox"

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if "t" in scrape_item.url.host or "_" in scrape_item.url.name:
            scrape_item.url = PRIMARY_URL / scrape_item.url.name.split("_")[0]

        elif "gallery/edit" in scrape_item.url.path:
            scrape_item.url = PRIMARY_URL / "g" / scrape_item.url.parts[-2]

        if "g" in scrape_item.url.parts:
            return await self.album(scrape_item)

        await self.image(scrape_item)

    @error_handling_wrapper
    async def album(self, scrape_item: ScrapeItem) -> None:
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.DOMAIN, scrape_item.url)

        if "The specified gallery could not be found" in soup.text:
            raise ScrapeError(404)

        album_id = scrape_item.url.parts[2]

        scrape_item.set_type(FILE_HOST_ALBUM, self.manager)
        title = css.select_one(soup, ALBUM_TITLE_SELECTOR).get_text(strip=True).rsplit(" - ", 1)[0]
        title = self.create_title(title, album_id)
        scrape_item.setup_as_album(title, album_id=album_id)

        for link in soup.select(IMAGES_SELECTOR):
            link_str: str = css.get_attr(link, "src").replace("thumbs", "images").replace("_b", "_o")
            link = self.parse_url(link_str)
            filename, ext = self.get_filename_and_ext(link.name)
            await self.handle_file(link, scrape_item, filename, ext)
            scrape_item.add_children()

    @error_handling_wrapper
    async def image(self, scrape_item: ScrapeItem) -> None:
        if await self.check_complete_from_referer(scrape_item):
            return

        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.DOMAIN, scrape_item.url)

        link_str: str = css.select_one_get_attr(soup, IMAGE_SELECTOR, "src")
        link = self.parse_url(link_str)
        filename, ext = self.get_filename_and_ext(link.name)
        await self.handle_file(link, scrape_item, filename, ext)
