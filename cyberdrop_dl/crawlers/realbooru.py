from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.utils import css
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem

CONTENT_SELECTOR = "div[class=items] div a"
VIDEO_SELECTOR = "video source"
IMAGE_SELECTOR = "img[id=image]"

PRIMARY_URL = AbsoluteHttpURL("https://realbooru.com")


class RealBooruCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {"File": "?id=...", "Tags": "?tags=..."}
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    NEXT_PAGE_SELECTOR: ClassVar[str] = "a[alt=next]"
    DOMAIN: ClassVar[str] = "realbooru"
    FOLDER_DOMAIN: ClassVar[str] = "RealBooru"

    async def async_startup(self) -> None:
        cookies = {"resize-original": "1"}
        self.update_cookies(cookies)

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if "tags" in scrape_item.url.query_string:
            return await self.tag(scrape_item)
        if "id" in scrape_item.url.query_string:
            return await self.file(scrape_item)
        raise ValueError

    @error_handling_wrapper
    async def tag(self, scrape_item: ScrapeItem) -> None:
        title_portion = scrape_item.url.query["tags"].strip()
        title = self.create_title(title_portion)
        scrape_item.setup_as_album(title)

        async for soup in self.web_pager(scrape_item.url, relative_to=scrape_item.url):
            for _, new_scrape_item in self.iter_children(scrape_item, soup, CONTENT_SELECTOR):
                self.manager.task_group.create_task(self.run(new_scrape_item))

    @error_handling_wrapper
    async def file(self, scrape_item: ScrapeItem) -> None:
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.DOMAIN, scrape_item.url)
        src_tag = soup.select_one(VIDEO_SELECTOR) or soup.select_one(IMAGE_SELECTOR)
        if not src_tag:
            raise ScrapeError(422)
        link = self.parse_url(css.get_attr(src_tag, "src"))
        filename, ext = self.get_filename_and_ext(link.name)
        await self.handle_file(link, scrape_item, filename, ext)
