from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils import css
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from cyberdrop_dl.data_structures.url_objects import ScrapeItem


class Selectors:
    CONTENT = "div[class=items] div a"
    VIDEO = "video source"
    IMAGE = "img[id=image]"
    IMAGE_OR_VIDEO = f"{IMAGE}, {VIDEO}"


_SELECTORS = Selectors()

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
            for _, new_scrape_item in self.iter_children(scrape_item, soup, _SELECTORS.CONTENT):
                self.create_task(self.run(new_scrape_item))

    @error_handling_wrapper
    async def file(self, scrape_item: ScrapeItem) -> None:
        soup = await self.request_soup(scrape_item.url)
        link_str = css.select_one_get_attr(soup, _SELECTORS.IMAGE_OR_VIDEO, "src")
        link = self.parse_url(link_str)
        filename, ext = self.get_filename_and_ext(link.name)
        await self.handle_file(link, scrape_item, filename, ext)
