from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils import css
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem


class Selectors:
    IMAGE = "img[id=img]"
    ALBUM_IMAGES = "div#gdt.gt200 a"
    DATE = "td[class=gdt2]"
    TITLE = "h1[id=gn]"
    NEXT_PAGE = "td[onclick='document.location=this.firstChild.href']:contains('>') a"


_SELECTORS = Selectors()

PRIMARY_URL = AbsoluteHttpURL("https://e-hentai.org/")


class EHentaiCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Album": "/g/...",
        "File": "/s/...",
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    NEXT_PAGE_SELECTOR: ClassVar[str] = _SELECTORS.NEXT_PAGE
    DOMAIN: ClassVar[str] = "e-hentai"
    FOLDER_DOMAIN: ClassVar[str] = "E-Hentai"

    def __post_init__(self) -> None:
        self._warnings_set = False

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if "g" in scrape_item.url.parts:
            return await self.album(scrape_item)
        if "s" in scrape_item.url.parts:
            return await self.image(scrape_item)
        raise ValueError

    @error_handling_wrapper
    async def album(self, scrape_item: ScrapeItem) -> None:
        async with self.startup_lock:
            if not self._warnings_set:
                await self.set_no_warnings(scrape_item)

        title: str = ""
        scrape_item.url = scrape_item.url.with_query(None)
        async for soup in self.web_pager(scrape_item.url):
            if not title:
                title = self.create_title(css.select_one_get_text(soup, _SELECTORS.TITLE))
                date_str: str = css.select_one_get_text(soup, _SELECTORS.DATE)
                gallery_id = scrape_item.url.parts[2]
                title = self.create_title(title, gallery_id)
                scrape_item.setup_as_album(title, album_id=gallery_id)
                scrape_item.possible_datetime = self.parse_date(date_str)

            for _, new_scrape_item in self.iter_children(scrape_item, soup, _SELECTORS.ALBUM_IMAGES):
                self.manager.task_group.create_task(self.run(new_scrape_item))

    @error_handling_wrapper
    async def image(self, scrape_item: ScrapeItem) -> None:
        if await self.check_complete_from_referer(scrape_item):
            return

        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.DOMAIN, scrape_item.url)

        link_str: str = css.select_one_get_attr(soup, _SELECTORS.IMAGE, "src")
        link = self.parse_url(link_str)
        filename, ext = self.get_filename_and_ext(link.name)
        custom_filename = self.create_custom_filename(scrape_item.url.name, ext)
        await self.handle_file(link, scrape_item, filename, ext, custom_filename=custom_filename)

    @error_handling_wrapper
    async def set_no_warnings(self, scrape_item: ScrapeItem) -> None:
        """Sets the no warnings cookie."""
        url = scrape_item.url.update_query(nw="session")
        async with self.request_limiter:
            await self.client.get_soup(self.DOMAIN, url)
        self._warnings_set = True
