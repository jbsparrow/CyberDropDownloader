from __future__ import annotations

from typing import TYPE_CHECKING

from yarl import URL

from cyberdrop_dl.clients.errors import ScrapeError
from cyberdrop_dl.crawlers.crawler import Crawler, create_task_id
from cyberdrop_dl.utils.utilities import error_handling_wrapper

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from cyberdrop_dl.managers.manager import Manager
    from cyberdrop_dl.utils.data_enums_classes.url_objects import ScrapeItem

CONTENT_SELECTOR = "div[class=image-list] span a"


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

        if "tags" in scrape_item.url.query_string:
            await self.tag(scrape_item)
        elif "id" in scrape_item.url.query_string:
            await self.file(scrape_item)
        else:
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

            content = soup.select(CONTENT_SELECTOR)
            for file_page in content:
                link_str: str = file_page.get("href")  # type: ignore
                link = self.parse_url(link_str)
                new_scrape_item = scrape_item.create_child(link)
                self.manager.task_group.create_task(self.run(new_scrape_item))
                scrape_item.add_children()

    @error_handling_wrapper
    async def file(self, scrape_item: ScrapeItem) -> None:
        """Scrapes an image."""
        async with self.request_limiter:
            soup: BeautifulSoup = await self.client.get_soup(self.domain, scrape_item.url)
        media_tag = soup.select_one("img[id=image]") or soup.select_one("video source")
        if not media_tag:
            raise ScrapeError(422)
        link_str: str = media_tag.get("src")
        link = self.parse_url(link_str)
        filename, ext = self.get_filename_and_ext(link.name)
        await self.handle_file(link, scrape_item, filename, ext)

    """~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"""

    async def set_cookies(self) -> None:
        """Sets the cookies for the client."""
        cookies = {"resize-original": "1"}
        self.update_cookies(cookies)
