from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.data_structures.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils import css
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from cyberdrop_dl.data_structures.url_objects import ScrapeItem


class Selectors:
    TITLE = "div#incflix-videowrap > h2"
    VIDEO = "div#incflix-videowrap source"
    NEXT = "table#incflix-pager a:-soup-contains('>')"
    VIDEO_THUMBS = "section#photos a"
    TAG_TITLE = "span#replaceTag1"


_SELECTORS = Selectors()

PRIMARY_URL = AbsoluteHttpURL("https://www.incestflix.com")


class IncestflixCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {"Video": "/watch/...", "Tag": "/tag/..."}
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    NEXT_PAGE_SELECTOR: ClassVar[str] = _SELECTORS.NEXT
    DOMAIN: ClassVar[str] = "incestflix"
    FOLDER_DOMAIN: ClassVar[str] = "IncestFlix"

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if "watch" in scrape_item.url.parts:
            return await self.video(scrape_item)
        if "tag" in scrape_item.url.parts:
            return await self.tag(scrape_item)
        raise ValueError

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem) -> None:
        if await self.check_complete_from_referer(scrape_item):
            return
        soup = await self.request_soup(scrape_item.url)
        title: str = css.select_one_get_text(soup, _SELECTORS.TITLE)
        link_str = css.select_one_get_attr(soup, _SELECTORS.VIDEO, "src")
        url = self.parse_url(link_str)
        filename, ext = self.get_filename_and_ext(f"{title}.mp4")
        await self.handle_file(scrape_item.url, scrape_item, filename, ext, debrid_link=url)

    @error_handling_wrapper
    async def tag(self, scrape_item: ScrapeItem) -> None:
        title_created: bool = False
        async for soup in self.web_pager(scrape_item.url):
            if not title_created:
                title = self.create_title(css.select_one(soup, _SELECTORS.TAG_TITLE).get_text(strip=True))
                scrape_item.setup_as_album(title)
                title_created = True
            for _, new_scrape_item in self.iter_children(scrape_item, soup, _SELECTORS.VIDEO_THUMBS):
                self.create_task(self.run(new_scrape_item))
