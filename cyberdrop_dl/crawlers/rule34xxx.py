from __future__ import annotations

from typing import TYPE_CHECKING

from yarl import URL

from cyberdrop_dl.crawlers.crawler import Crawler, create_task_id
from cyberdrop_dl.exceptions import ScrapeError
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.data_structures.url_objects import ScrapeItem
    from cyberdrop_dl.managers.manager import Manager


class Selector:
    CONTENT = "div[class=image-list] span a"
    IMAGE = "img[id=image]"
    VIDEO = "video source"
    DATE = "li:contains('Posted: ')"


_SELECTOR = Selector()


class Rule34XXXCrawler(Crawler):
    primary_base_domain = URL("https://rule34.xxx")
    next_page_selector = "a[alt=next]"

    def __init__(self, manager: Manager) -> None:
        super().__init__(manager, "rule34.xxx", "Rule34XXX")

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    async def async_startup(self) -> None:
        await self.set_cookies()

    @create_task_id
    async def fetch(self, scrape_item: ScrapeItem) -> None:
        """Determines where to send the scrape item based on the url."""

        if scrape_item.url.query.get("tags"):
            return await self.tag(scrape_item)
        if scrape_item.url.query.get("id"):
            return await self.file(scrape_item)
        raise ValueError

    @error_handling_wrapper
    async def tag(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an album."""
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
        """Scrapes an image."""
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url)

        media_tag = soup.select_one(_SELECTOR.IMAGE) or soup.select_one(_SELECTOR.VIDEO)
        if not media_tag:
            raise ScrapeError(422)

        if date_tag := soup.select_one(_SELECTOR.DATE):
            scrape_item.possible_datetime = self.parse_date(date_tag.get_text(strip=True).removeprefix("Posted: "))
        link_str: str = media_tag["src"]  # type: ignore
        link = self.parse_url(link_str)
        filename, ext = self.get_filename_and_ext(link.name)
        await self.handle_file(link, scrape_item, filename, ext)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    async def set_cookies(self) -> None:
        """Sets the cookies for the client."""
        cookies = {"resize-original": "1"}
        self.update_cookies(cookies)
