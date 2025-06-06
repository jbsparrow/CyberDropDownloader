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

PRIMARY_URL = AbsoluteHttpURL("https://rule34.xxx")


class Selector:
    CONTENT = "div[class=image-list] span a"
    IMAGE = "img[id=image]"
    VIDEO = "video source"
    DATE = "li:contains('Posted: ')"


_SELECTOR = Selector()


class Rule34XXXCrawler(Crawler):
    SUPPORTED_PATHS: ClassVar[SupportedPaths] = {"File": "?id=...", "Tag": "?tags=..."}
    PRIMARY_URL: ClassVar[AbsoluteHttpURL] = PRIMARY_URL
    NEXT_PAGE_SELECTOR: ClassVar[str] = "a[alt=next]"
    DOMAIN: ClassVar[str] = "rule34.xxx"
    FOLDER_DOMAIN: ClassVar[str] = "Rule34XXX"

    async def async_startup(self) -> None:
        self.set_cookies()

    async def fetch(self, scrape_item: ScrapeItem) -> None:
        if scrape_item.url.query.get("tags"):
            return await self.tag(scrape_item)
        if scrape_item.url.query.get("id"):
            return await self.file(scrape_item)
        raise ValueError

    @error_handling_wrapper
    async def tag(self, scrape_item: ScrapeItem) -> None:
        title: str = ""
        async for soup in self.web_pager(scrape_item.url, relative_to=scrape_item.url):
            if not title:
                title_portion = scrape_item.url.query["tags"].strip()
                title = self.create_title(title_portion)
                scrape_item.setup_as_album(title)

            for _, new_scrape_item in self.iter_children(scrape_item, soup, _SELECTOR.CONTENT):
                self.manager.task_group.create_task(self.run(new_scrape_item))

    @error_handling_wrapper
    async def file(self, scrape_item: ScrapeItem) -> None:
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.DOMAIN, scrape_item.url)

        media_tag = soup.select_one(_SELECTOR.IMAGE) or soup.select_one(_SELECTOR.VIDEO)
        if not media_tag:
            raise ScrapeError(422)

        if date_tag := soup.select_one(_SELECTOR.DATE):
            date_str = date_tag.get_text(strip=True).removeprefix("Posted: ")
            scrape_item.possible_datetime = self.parse_date(date_str)
        link_str: str = css.get_attr(media_tag, "src")
        link = self.parse_url(link_str)
        filename, ext = self.get_filename_and_ext(link.name)
        await self.handle_file(link, scrape_item, filename, ext)

    def set_cookies(self) -> None:
        cookies = {"resize-original": "1"}
        self.update_cookies(cookies)
