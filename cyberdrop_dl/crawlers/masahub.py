from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from cyberdrop_dl.crawlers.crawler import Crawler, SupportedPaths
from cyberdrop_dl.url_objects import AbsoluteHttpURL
from cyberdrop_dl.utils import css, json_ld
from cyberdrop_dl.utils.errors import error_handling_wrapper

if TYPE_CHECKING:
    from cyberdrop_dl.url_objects import ScrapeItem


class Selector:
    VIDEO_SRC = css.CssAttributeSelector("a.video-btn, a.download-btn", "href")
    TITLE = "div.posts > h1 > strong, div.video_page_toolbar > h1"
    NEXT_PAGE = "div > a:-soup-contains('Next')"
    VIDEOS = "a.title, div.title > a"


class MasahubCrawler(Crawler):
    SUPPORTED_DOMAINS = "masa49.com", "masahub.com", "masahub2.com", "masafun.net", "lol49.com", "vido99.com"
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {
        "Videos": "/title",
        "Search": "?s=<query>",
    }
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = AbsoluteHttpURL("https://masahub.com")
    DOMAIN: ClassVar[str] = "masahub.com"
    FOLDER_DOMAIN: ClassVar[str] = "Masahub"
    NEXT_PAGE_SELECTOR: ClassVar[str] = Selector.NEXT_PAGE

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if query := scrape_item.url.query.get("s"):
            return await self.search(scrape_item, query)
        if len(scrape_item.url.parts) >= 2:
            return await self.video(scrape_item)
        raise ValueError

    @error_handling_wrapper
    async def video(self, scrape_item: ScrapeItem) -> None:
        if await self.check_complete_from_referer(scrape_item.url):
            return None

        soup = await self.request_soup(scrape_item.url)
        link = self.parse_url(Selector.VIDEO_SRC(soup))
        title = css.select_text(soup, Selector.TITLE)
        _, ext = self.get_filename_and_ext(link.name)
        scrape_item.uploaded_at = json_ld.upload_date(soup)
        custom_filename = self.create_custom_filename(title, ext)
        return await self.handle_file(link, scrape_item, link.name, ext, custom_filename=custom_filename)

    @error_handling_wrapper
    async def search(self, scrape_item: ScrapeItem, query: str) -> None:
        title = self.create_title(query)
        scrape_item.setup_as_album(title)
        async for soup in self.web_pager(scrape_item.url):
            for new_scrape_item in self.iter_children(scrape_item, soup, Selector.VIDEOS):
                self.create_task(self.run(new_scrape_item))
